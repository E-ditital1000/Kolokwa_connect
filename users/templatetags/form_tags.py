from django import template
from django.forms.boundfield import BoundField

register = template.Library()

@register.filter(name='add_class')
def add_class(value, arg):
    # Only apply if it's a BoundField
    if isinstance(value, BoundField):
        return value.as_widget(attrs={'class': arg})
    # Otherwise return as is
    return value