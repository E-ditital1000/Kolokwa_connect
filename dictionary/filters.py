import django_filters
from .models import KoloquaEntry, WordCategory

class KoloquaEntryFilter(django_filters.FilterSet):
    entry_type = django_filters.ChoiceFilter(choices=KoloquaEntry.ENTRY_TYPES)
    status = django_filters.ChoiceFilter(choices=KoloquaEntry.STATUS_CHOICES)
    categories = django_filters.ModelMultipleChoiceFilter(
        queryset=WordCategory.objects.all(),
        field_name='categories__id',
        to_field_name='id'
    )
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    min_upvotes = django_filters.NumberFilter(field_name='upvotes', lookup_expr='gte')
    
    class Meta:
        model = KoloquaEntry
        fields = ['entry_type', 'status', 'categories', 'contributor']