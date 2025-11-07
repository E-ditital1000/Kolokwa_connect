import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import pg from "pg";
import OpenAI from "openai";

const { Pool } = pg;

// ---------------------------------------------------------------
// Enhanced Kolokwa Dictionary MCP Server (TypeScript)
// ---------------------------------------------------------------
// Provides dictionary lookup, translation, phrase construction,
// and AI-powered language assistance for the Liberian Kolokwa 
// Dictionary platform.
// ---------------------------------------------------------------

const pool = new Pool({
  host: process.env.DATABASE_HOST || "localhost",
  port: parseInt(process.env.DATABASE_PORT || "5432"),
  user: process.env.DATABASE_USER || "postgres",
  password: process.env.DATABASE_PASSWORD || "",
  database: process.env.DATABASE_NAME || "kolokwa_db",
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 10000,
});

// Initialize OpenAI client if API key is available
const openai = process.env.OPENAI_API_KEY 
  ? new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
  : null;

interface DictionaryEntry {
  id: number;
  kolokwa: string;
  english: string;
  literal: string | null;
  type: string;
  context: string | null;
  example_kolokwa: string | null;
  example_english: string | null;
  pronunciation: string | null;
  cultural_notes: string | null;
  score: number;
}

interface SearchResult {
  success: boolean;
  count?: number;
  entries?: DictionaryEntry[];
  error?: string;
}

interface TranslationResult {
  success: boolean;
  translation?: string;
  breakdown?: Array<{ kolokwa: string; english: string }>;
  confidence?: string;
  notes?: string;
  error?: string;
}

interface PhraseResult {
  success: boolean;
  phrase?: string;
  components?: Array<{ word: string; translation: string; pronunciation?: string }>;
  example?: string;
  cultural_note?: string;
  error?: string;
}

interface CategoryResult {
  success: boolean;
  categories?: Array<{ id: number; name: string; description: string; entry_count: number }>;
  error?: string;
}

interface PopularResult {
  success: boolean;
  entries?: DictionaryEntry[];
  error?: string;
}

interface NLQueryResult {
  success: boolean;
  response?: string;
  intent?: string;
  entries_used?: number;
  error?: string;
}

// Initialize MCP Server
const server = new Server(
  {
    name: "kolokwa-dictionary",
    version: "2.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// ========== EXISTING TOOLS ==========

async function searchKolokwa(
  query: string,
  searchType: string = "all",
  limit: number = 10
): Promise<SearchResult> {
  limit = Math.min(limit, 50);
  query = query.trim();

  if (!query) {
    return { success: false, error: "Query cannot be empty." };
  }

  const SQL_QUERIES: { [key: string]: string } = {
    kolokwa: `SELECT * FROM koloqua_entries
              WHERE status='verified' AND (koloqua_text ILIKE $1 OR example_sentence_koloqua ILIKE $1)
              ORDER BY upvotes - downvotes DESC, created_at DESC LIMIT $2`,
    english: `SELECT * FROM koloqua_entries
              WHERE status='verified' AND (english_translation ILIKE $1 OR example_sentence_english ILIKE $1)
              ORDER BY upvotes - downvotes DESC, created_at DESC LIMIT $2`,
    all: `SELECT * FROM koloqua_entries
          WHERE status='verified' AND (
            koloqua_text ILIKE $1 OR english_translation ILIKE $1 OR
            example_sentence_koloqua ILIKE $1 OR example_sentence_english ILIKE $1 OR
            context_explanation ILIKE $1 OR cultural_notes ILIKE $1
          )
          ORDER BY upvotes - downvotes DESC, created_at DESC LIMIT $2`,
  };

  const sql = SQL_QUERIES[searchType] || SQL_QUERIES["all"];

  try {
    const result = await pool.query(sql, [`%${query}%`, limit]);

    const entries: DictionaryEntry[] = result.rows.map((r) => ({
      id: r.id,
      kolokwa: r.koloqua_text,
      english: r.english_translation,
      literal: r.literal_translation,
      type: r.entry_type,
      context: r.context_explanation,
      example_kolokwa: r.example_sentence_koloqua,
      example_english: r.example_sentence_english,
      pronunciation: r.pronunciation_guide,
      cultural_notes: r.cultural_notes,
      score: (r.upvotes || 0) - (r.downvotes || 0),
    }));

    return { success: true, count: entries.length, entries };
  } catch (error) {
    console.error("Search error:", error);
    return { success: false, error: String(error) };
  }
}

async function healthCheck() {
  try {
    await pool.query("SELECT 1");
    const aiStatus = openai ? "available" : "not_configured";
    return { 
      success: true, 
      status: "healthy", 
      database: "connected",
      ai_translation: aiStatus
    };
  } catch (error) {
    console.warn("Health check issue:", error);
    return {
      success: true,
      status: "running",
      database: `not_connected (${error})`,
      ai_translation: openai ? "available" : "not_configured"
    };
  }
}

async function getEntryDetail(entryId: number) {
  try {
    const result = await pool.query(
      "SELECT * FROM koloqua_entries WHERE id = $1 AND status='verified'",
      [entryId]
    );

    if (result.rows.length === 0) {
      return { success: false, error: "Entry not found or not verified." };
    }

    const entry = result.rows[0];
    entry.score = (entry.upvotes || 0) - (entry.downvotes || 0);

    return { success: true, entry };
  } catch (error) {
    console.error("Error retrieving entry detail:", error);
    return { success: false, error: String(error) };
  }
}

// ========== NEW TOOLS ==========

async function translatePhrase(
  phrase: string,
  fromLanguage: string = "english",
  toLanguage: string = "kolokwa"
): Promise<TranslationResult> {
  if (!phrase || phrase.trim().length === 0) {
    return { success: false, error: "Phrase cannot be empty." };
  }

  try {
    // Search for words in the phrase
    const words = phrase.toLowerCase().split(/\s+/).filter(w => w.length > 0);
    const breakdown: Array<{ kolokwa: string; english: string }> = [];
    
    // Try to find each word in dictionary
    for (const word of words) {
      const searchResult = await searchKolokwa(word, fromLanguage, 1);
      if (searchResult.entries && searchResult.entries.length > 0) {
        const entry = searchResult.entries[0];
        breakdown.push({
          kolokwa: entry.kolokwa,
          english: entry.english
        });
      }
    }

    if (breakdown.length === 0) {
      return {
        success: true,
        translation: null,
        breakdown: [],
        confidence: "low",
        notes: `No dictionary entries found for "${phrase}". This phrase may need to be added to the dictionary.`
      };
    }

    // Build translation from components
    const translation = fromLanguage === "english" 
      ? breakdown.map(b => b.kolokwa).join(" ")
      : breakdown.map(b => b.english).join(" ");

    const confidence = breakdown.length === words.length ? "high" : "partial";
    const notes = breakdown.length < words.length 
      ? `Found translations for ${breakdown.length} of ${words.length} words.`
      : undefined;

    return {
      success: true,
      translation,
      breakdown,
      confidence,
      notes
    };
  } catch (error) {
    console.error("Translation error:", error);
    return { success: false, error: String(error) };
  }
}

async function constructPhrase(
  words: string[],
  language: string = "english"
): Promise<PhraseResult> {
  if (!words || words.length === 0) {
    return { success: false, error: "Words array cannot be empty." };
  }

  try {
    const components: Array<{ 
      word: string; 
      translation: string; 
      pronunciation?: string 
    }> = [];

    // Look up each word
    for (const word of words) {
      const searchResult = await searchKolokwa(word.trim(), language, 1);
      if (searchResult.entries && searchResult.entries.length > 0) {
        const entry = searchResult.entries[0];
        components.push({
          word: language === "english" ? entry.english : entry.kolokwa,
          translation: language === "english" ? entry.kolokwa : entry.english,
          pronunciation: entry.pronunciation
        });
      }
    }

    if (components.length === 0) {
      return {
        success: false,
        error: "No dictionary entries found for the provided words."
      };
    }

    const phrase = components.map(c => c.translation).join(" ");

    return {
      success: true,
      phrase,
      components
    };
  } catch (error) {
    console.error("Phrase construction error:", error);
    return { success: false, error: String(error) };
  }
}

async function getCategories(): Promise<CategoryResult> {
  try {
    const result = await pool.query(`
      SELECT 
        wc.id,
        wc.name,
        wc.description,
        COUNT(DISTINCT ke.id) as entry_count
      FROM word_categories wc
      LEFT JOIN koloqua_entries_categories kec ON wc.id = kec.wordcategory_id
      LEFT JOIN koloqua_entries ke ON kec.koloquaentry_id = ke.id AND ke.status = 'verified'
      GROUP BY wc.id, wc.name, wc.description
      ORDER BY wc.name
    `);

    const categories = result.rows.map(r => ({
      id: r.id,
      name: r.name,
      description: r.description || "",
      entry_count: parseInt(r.entry_count) || 0
    }));

    return { success: true, categories };
  } catch (error) {
    console.error("Error fetching categories:", error);
    return { success: false, error: String(error) };
  }
}

async function getEntriesByCategory(
  categoryId: number,
  limit: number = 20
): Promise<SearchResult> {
  try {
    const result = await pool.query(`
      SELECT DISTINCT ke.*
      FROM koloqua_entries ke
      JOIN koloqua_entries_categories kec ON ke.id = kec.koloquaentry_id
      WHERE kec.wordcategory_id = $1 AND ke.status = 'verified'
      ORDER BY ke.upvotes - ke.downvotes DESC, ke.created_at DESC
      LIMIT $2
    `, [categoryId, limit]);

    const entries: DictionaryEntry[] = result.rows.map((r) => ({
      id: r.id,
      kolokwa: r.koloqua_text,
      english: r.english_translation,
      literal: r.literal_translation,
      type: r.entry_type,
      context: r.context_explanation,
      example_kolokwa: r.example_sentence_koloqua,
      example_english: r.example_sentence_english,
      pronunciation: r.pronunciation_guide,
      cultural_notes: r.cultural_notes,
      score: (r.upvotes || 0) - (r.downvotes || 0),
    }));

    return { success: true, count: entries.length, entries };
  } catch (error) {
    console.error("Error fetching entries by category:", error);
    return { success: false, error: String(error) };
  }
}

async function getPopularEntries(limit: number = 10): Promise<PopularResult> {
  try {
    limit = Math.min(limit, 50);
    
    const result = await pool.query(`
      SELECT *
      FROM koloqua_entries
      WHERE status = 'verified'
      ORDER BY (upvotes - downvotes) DESC, upvotes DESC
      LIMIT $1
    `, [limit]);

    const entries: DictionaryEntry[] = result.rows.map((r) => ({
      id: r.id,
      kolokwa: r.koloqua_text,
      english: r.english_translation,
      literal: r.literal_translation,
      type: r.entry_type,
      context: r.context_explanation,
      example_kolokwa: r.example_sentence_koloqua,
      example_english: r.example_sentence_english,
      pronunciation: r.pronunciation_guide,
      cultural_notes: r.cultural_notes,
      score: (r.upvotes || 0) - (r.downvotes || 0),
    }));

    return { success: true, entries };
  } catch (error) {
    console.error("Error fetching popular entries:", error);
    return { success: false, error: String(error) };
  }
}

async function getRecentEntries(limit: number = 10): Promise<PopularResult> {
  try {
    limit = Math.min(limit, 50);
    
    const result = await pool.query(`
      SELECT *
      FROM koloqua_entries
      WHERE status = 'verified'
      ORDER BY created_at DESC
      LIMIT $1
    `, [limit]);

    const entries: DictionaryEntry[] = result.rows.map((r) => ({
      id: r.id,
      kolokwa: r.koloqua_text,
      english: r.english_translation,
      literal: r.literal_translation,
      type: r.entry_type,
      context: r.context_explanation,
      example_kolokwa: r.example_sentence_koloqua,
      example_english: r.example_sentence_english,
      pronunciation: r.pronunciation_guide,
      cultural_notes: r.cultural_notes,
      score: (r.upvotes || 0) - (r.downvotes || 0),
    }));

    return { success: true, entries };
  } catch (error) {
    console.error("Error fetching recent entries:", error);
    return { success: false, error: String(error) };
  }
}

async function naturalLanguageQuery(
  query: string,
  includeExamples: boolean = true,
  culturalContext: boolean = true
): Promise<NLQueryResult> {
  if (!openai) {
    return {
      success: false,
      error: "AI translation not configured. Please set OPENAI_API_KEY environment variable."
    };
  }

  if (!query || query.trim().length === 0) {
    return { success: false, error: "Query cannot be empty." };
  }

  try {
    // Search dictionary for relevant entries
    const searchResult = await searchKolokwa(query, "all", 10);
    
    if (!searchResult.entries || searchResult.entries.length === 0) {
      return {
        success: true,
        response: `I couldn't find any entries matching "${query}" in the Kolokwa dictionary. The dictionary is still growing - consider contributing this translation!`,
        intent: "not_found",
        entries_used: 0
      };
    }

    // Format entries for AI context
    const entriesContext = searchResult.entries.map((e, i) => `
Entry ${i + 1}:
- Kolokwa: ${e.kolokwa}
- English: ${e.english}
${e.literal ? `- Literal: ${e.literal}` : ''}
${e.pronunciation ? `- Pronunciation: ${e.pronunciation}` : ''}
${includeExamples && e.example_kolokwa ? `- Example: "${e.example_kolokwa}" = "${e.example_english}"` : ''}
${culturalContext && e.cultural_notes ? `- Cultural note: ${e.cultural_notes}` : ''}
${e.context ? `- Context: ${e.context}` : ''}
    `.trim()).join('\n\n');

    // Get AI response
    const completion = await openai.chat.completions.create({
      model: "gpt-4-turbo-preview",
      messages: [
        {
          role: "system",
          content: "You are a helpful Kolokwa dictionary assistant. Use ONLY the verified dictionary entries provided. Be accurate and culturally respectful. Kolokwa is a LIBERIAN language, not Nigerian Pidgin."
        },
        {
          role: "user",
          content: `User query: "${query}"\n\nAvailable dictionary entries:\n${entriesContext}\n\nProvide a helpful, natural response using only these verified entries. Include examples when relevant.`
        }
      ],
      temperature: 0.7,
      max_tokens: 500
    });

    const response = completion.choices[0].message.content?.trim() || "Unable to generate response.";

    return {
      success: true,
      response,
      intent: "general",
      entries_used: searchResult.entries.length
    };
  } catch (error) {
    console.error("Natural language query error:", error);
    return { success: false, error: String(error) };
  }
}

// ========== REGISTER TOOLS ==========

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "search_kolokwa",
        description:
          "Search the Kolokwa dictionary for words, phrases, or translations. Returns verified entries sorted by popularity.",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "The search term to look up in the dictionary",
            },
            search_type: {
              type: "string",
              enum: ["all", "kolokwa", "english"],
              description:
                "Search in Kolokwa words, English translations, or all fields",
              default: "all",
            },
            limit: {
              type: "number",
              description: "Maximum number of results to return (max 50)",
              default: 10,
            },
          },
          required: ["query"],
        },
      },
      {
        name: "translate_phrase",
        description:
          "Translate a phrase between English and Kolokwa by looking up individual words and combining them. Shows word-by-word breakdown.",
        inputSchema: {
          type: "object",
          properties: {
            phrase: {
              type: "string",
              description: "The phrase to translate",
            },
            from_language: {
              type: "string",
              enum: ["english", "kolokwa"],
              description: "Source language",
              default: "english",
            },
            to_language: {
              type: "string",
              enum: ["kolokwa", "english"],
              description: "Target language",
              default: "kolokwa",
            },
          },
          required: ["phrase"],
        },
      },
      {
        name: "construct_phrase",
        description:
          "Build a Kolokwa phrase from multiple English words or vice versa. Provides pronunciation guides for each component.",
        inputSchema: {
          type: "object",
          properties: {
            words: {
              type: "array",
              items: { type: "string" },
              description: "Array of words to combine into a phrase",
            },
            language: {
              type: "string",
              enum: ["english", "kolokwa"],
              description: "Language of the input words",
              default: "english",
            },
          },
          required: ["words"],
        },
      },
      {
        name: "get_categories",
        description:
          "Get all word categories in the dictionary with entry counts. Useful for browsing the dictionary by topic.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "get_entries_by_category",
        description:
          "Get all dictionary entries in a specific category. Returns popular entries first.",
        inputSchema: {
          type: "object",
          properties: {
            category_id: {
              type: "number",
              description: "The ID of the category to fetch entries from",
            },
            limit: {
              type: "number",
              description: "Maximum number of entries to return (max 50)",
              default: 20,
            },
          },
          required: ["category_id"],
        },
      },
      {
        name: "get_popular_entries",
        description:
          "Get the most popular dictionary entries based on community votes. Great for learning common words first.",
        inputSchema: {
          type: "object",
          properties: {
            limit: {
              type: "number",
              description: "Number of popular entries to return (max 50)",
              default: 10,
            },
          },
        },
      },
      {
        name: "get_recent_entries",
        description:
          "Get recently added dictionary entries. See what's new in the dictionary.",
        inputSchema: {
          type: "object",
          properties: {
            limit: {
              type: "number",
              description: "Number of recent entries to return (max 50)",
              default: 10,
            },
          },
        },
      },
      {
        name: "natural_language_query",
        description:
          "Ask natural language questions about Kolokwa translations, meanings, or usage. Uses AI to provide contextual answers from verified dictionary entries.",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Natural language question or translation request",
            },
            include_examples: {
              type: "boolean",
              description: "Include example sentences in the response",
              default: true,
            },
            cultural_context: {
              type: "boolean",
              description: "Include cultural notes and context",
              default: true,
            },
          },
          required: ["query"],
        },
      },
      {
        name: "get_entry_detail",
        description:
          "Retrieve full details for a specific dictionary entry by ID",
        inputSchema: {
          type: "object",
          properties: {
            entry_id: {
              type: "number",
              description: "The unique ID of the dictionary entry",
            },
          },
          required: ["entry_id"],
        },
      },
      {
        name: "health_check",
        description:
          "Check if the MCP server, database connection, and AI features are healthy",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ],
  };
});

// ========== HANDLE TOOL CALLS ==========

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    let result;

    switch (name) {
      case "search_kolokwa":
        if (!args) throw new Error("Missing arguments for search_kolokwa");
        result = await searchKolokwa(
          args.query as string,
          args.search_type as string,
          args.limit as number
        );
        break;

      case "translate_phrase":
        if (!args) throw new Error("Missing arguments for translate_phrase");
        result = await translatePhrase(
          args.phrase as string,
          args.from_language as string,
          args.to_language as string
        );
        break;

      case "construct_phrase":
        if (!args) throw new Error("Missing arguments for construct_phrase");
        result = await constructPhrase(
          args.words as string[],
          args.language as string
        );
        break;

      case "get_categories":
        result = await getCategories();
        break;

      case "get_entries_by_category":
        if (!args) throw new Error("Missing arguments for get_entries_by_category");
        result = await getEntriesByCategory(
          args.category_id as number,
          args.limit as number
        );
        break;

      case "get_popular_entries":
        result = await getPopularEntries(args?.limit as number);
        break;

      case "get_recent_entries":
        result = await getRecentEntries(args?.limit as number);
        break;

      case "natural_language_query":
        if (!args) throw new Error("Missing arguments for natural_language_query");
        result = await naturalLanguageQuery(
          args.query as string,
          args.include_examples as boolean,
          args.cultural_context as boolean
        );
        break;

      case "get_entry_detail":
        if (!args) throw new Error("Missing arguments for get_entry_detail");
        result = await getEntryDetail(args.entry_id as number);
        break;

      case "health_check":
        result = await healthCheck();
        break;

      default:
        throw new Error(`Unknown tool: ${name}`);
    }

    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ success: false, error: String(error) }),
        },
      ],
      isError: true,
    };
  }
});

// ========== START SERVER ==========

async function main() {
  console.log("Starting Enhanced Kolokwa Dictionary MCP Server...");
  console.log(`Database host: ${process.env.DATABASE_HOST || "localhost"}`);
  console.log(`AI Translation: ${openai ? "Enabled" : "Disabled (set OPENAI_API_KEY to enable)"}`);

  const transport = new StdioServerTransport();
  await server.connect(transport);

  console.log("Kolokwa Dictionary MCP Server running on stdio");
}

main().catch((error) => {
  console.error("Fatal server error:", error);
  process.exit(1);
});