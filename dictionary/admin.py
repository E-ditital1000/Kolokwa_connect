from django.contrib import admin
from .models import KoloquaEntry, WordCategory, EntryVerification, EntryVote, TranslationHistory

@admin.register(WordCategory)
class WordCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name']


@admin.register(KoloquaEntry)
class KoloquaEntryAdmin(admin.ModelAdmin):
    list_display = ['koloqua_text', 'english_translation', 'entry_type', 'status', 'contributor', 'created_at']
    list_filter = ['status', 'entry_type', 'created_at']
    search_fields = ['koloqua_text', 'english_translation']
    readonly_fields = ['upvotes', 'downvotes', 'verification_count', 'created_at', 'updated_at']
    filter_horizontal = ['categories']
    
    actions = ['mark_as_verified', 'mark_as_rejected']
    
    def mark_as_verified(self, request, queryset):
        queryset.update(status='verified')
    mark_as_verified.short_description = "Mark selected entries as Verified"

    def mark_as_rejected(self, request, queryset):
        queryset.update(status='rejected')
    mark_as_rejected.short_description = "Mark selected entries as Rejected"