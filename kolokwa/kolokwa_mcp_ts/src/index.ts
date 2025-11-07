import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import pg from "pg";

const { Pool } = pg;

// ---------------------------------------------------------------
// Kolokwa Dictionary MCP Server (TypeScript)
// ---------------------------------------------------------------
// Provides dictionary lookup, translation, and health monitoring
// for the Liberian Kolokwa Dictionary platform.
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

interface HealthCheckResult {
  success: boolean;
  status: string;
  database: string;
}

interface EntryDetailResult {
  success: boolean;
  entry?: any;
  error?: string;
}

// Initialize MCP Server
const server = new Server(
  {
    name: "kolokwa-dictionary",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Tool: search_kolokwa
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

// Tool: health_check
async function healthCheck(): Promise<HealthCheckResult> {
  try {
    await pool.query("SELECT 1");
    return { success: true, status: "healthy", database: "connected" };
  } catch (error) {
    console.warn("Health check issue:", error);
    return {
      success: true,
      status: "running",
      database: `not_connected (${error})`,
    };
  }
}

// Tool: get_entry_detail
async function getEntryDetail(entryId: number): Promise<EntryDetailResult> {
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

// Register tools with the server
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
        name: "health_check",
        description:
          "Check if the MCP server and database connection are healthy",
        inputSchema: {
          type: "object",
          properties: {},
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
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    if (name === "search_kolokwa") {
      if (!args) {
        throw new Error("Missing arguments for search_kolokwa");
      }
      const result = await searchKolokwa(
        args.query as string,
        args.search_type as string,
        args.limit as number
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } else if (name === "health_check") {
      const result = await healthCheck();
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } else if (name === "get_entry_detail") {
      if (!args) {
        throw new Error("Missing arguments for get_entry_detail");
      }
      const result = await getEntryDetail(args.entry_id as number);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } else {
      throw new Error(`Unknown tool: ${name}`);
    }
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

// Start the server
async function main() {
  console.log("Starting Kolokwa Dictionary MCP Server...");
  console.log(`Database host: ${process.env.DATABASE_HOST || "localhost"}`);

  const transport = new StdioServerTransport();
  await server.connect(transport);

  console.log("Kolokwa Dictionary MCP Server running on stdio");
}

main().catch((error) => {
  console.error("Fatal server error:", error);
  process.exit(1);
});