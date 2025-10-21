from django import template
from django.forms.boundfield import BoundField

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    """
    Add CSS class to form field widget
    Usage: {{ form.field|add_class:"form-control" }}
    """
    if isinstance(field, BoundField):
        existing_classes = field.field.widget.attrs.get('class', '')
        if existing_classes:
            css_class = f"{existing_classes} {css_class}"
        return field.as_widget(attrs={'class': css_class})
    return field


@register.filter(name='add_placeholder')
def add_placeholder(field, placeholder):
    """
    Add placeholder to form field
    Usage: {{ form.field|add_placeholder:"Enter text" }}
    """
    if isinstance(field, BoundField):
        return field.as_widget(attrs={'placeholder': placeholder})
    return field


@register.filter(name='add_attrs')
def add_attrs(field, attrs):
    """
    Add multiple attributes to form field
    Usage: {{ form.field|add_attrs:"class:form-control,placeholder:Enter text" }}
    """
    if isinstance(field, BoundField):
        attr_dict = {}
        for attr in attrs.split(','):
            key, val = attr.split(':')
            attr_dict[key.strip()] = val.strip()
        return field.as_widget(attrs=attr_dict)
    return field