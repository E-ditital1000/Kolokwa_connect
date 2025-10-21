from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import ValidationError

User = get_user_model()


class UserProfileForm(forms.ModelForm):
    """Form for editing user profile"""
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'bio', 'profile_picture', 'phone_number'
        ]
        widgets = {
            'bio': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Tell us about yourself...',
                'class': 'form-control'
            }),
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Choose a username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your@email.com'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your last name'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+231 88 555 0000'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/jpeg,image/jpg,image/png,image/gif,image/webp'
            }),
        }
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            # Check if username is taken by another user
            existing = User.objects.filter(username=username).exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError('This username is already taken.')
        return username
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if email is taken by another user
            existing = User.objects.filter(email=email).exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError('This email is already registered.')
        return email
    
    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        
        # If no new picture uploaded, return existing
        if not picture:
            return picture
        
        # Check if it's a file upload (not just a string path)
        if hasattr(picture, 'size'):
            # Check file size (limit to 5MB)
            if picture.size > 5 * 1024 * 1024:
                raise ValidationError('Image file too large ( > 5MB )')
            
            # Check file type by extension
            valid_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp']
            import os
            ext = os.path.splitext(picture.name)[1][1:].lower()
            if ext not in valid_extensions:
                raise ValidationError(f'Unsupported file extension. Use: {", ".join(valid_extensions)}')
            
            # Try to validate with Pillow if available
            try:
                from PIL import Image
                # Open and verify the image
                img = Image.open(picture)
                img.verify()
                # Reset file pointer after verify
                picture.seek(0)
            except ImportError:
                # Pillow not installed, skip image validation
                pass
            except Exception as e:
                raise ValidationError(f'Invalid image file: {str(e)}')
        
        return picture


class UserRegistrationForm(forms.ModelForm):
    """Form for user registration"""
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter password'
        })
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password'
        })
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Choose a username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your@email.com'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last name'
            }),
        }
    
    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords don't match")
        return password2
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user