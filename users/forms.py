from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()

# Role choices for admin (staff only — patient accounts are created by doctors)
STAFF_ROLE_CHOICES = [
    (value, label) for value, label in User.ROLE_CHOICES if value != 'patient'
]


class UserProfileForm(forms.ModelForm):
    """Formulaire d'auto-édition du profil — sans champ role (non modifiable par l'utilisateur lui-même)."""
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'contact', 'specialite', 'photo']
        widgets = {
            'username':   forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'contact':    forms.TextInput(attrs={'class': 'form-control'}),
            'specialite': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Cardiologie, Diabétologie…'}),
            'photo':      forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.role == 'doctor':
            if not cleaned_data.get('specialite'):
                self.add_error('specialite', "La spécialité est obligatoire pour un médecin.")
        return cleaned_data


class UserForm(forms.ModelForm):
    """Formulaire admin : édition complète d'un utilisateur (rôle modifiable)."""
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'contact', 'specialite', 'role', 'photo']
        widgets = {
            'username':   forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'contact':    forms.TextInput(attrs={'class': 'form-control'}),
            'specialite': forms.TextInput(attrs={'class': 'form-control'}),
            'role':       forms.Select(attrs={'class': 'form-select'}),
            'photo':      forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        specialite = cleaned_data.get('specialite')
        if role == 'doctor' and not specialite:
            self.add_error('specialite', "La spécialité est obligatoire pour un médecin.")
        return cleaned_data


class UserRegisterForm(forms.ModelForm):
    """
    Formulaire admin : créer un compte personnel (admin/médecin/infirmier/pharmacien/labo).
    Le rôle 'patient' est exclu — les comptes patients sont créés par les médecins.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=True, min_length=6, label="Mot de passe",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=True, label="Confirmer le mot de passe",
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role', 'contact', 'specialite', 'photo']
        widgets = {
            'username':   forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'contact':    forms.TextInput(attrs={'class': 'form-control'}),
            'specialite': forms.TextInput(attrs={'class': 'form-control'}),
            'role':       forms.Select(attrs={'class': 'form-select'}),
            'photo':      forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Admin creates staff accounts only — patient accounts are created by doctors
        # Empty first option forces explicit role selection (prevents accidental admin creation)
        self.fields['role'].choices = [('', '— Sélectionner un rôle —')] + STAFF_ROLE_CHOICES

    def clean_username(self):
        return self.cleaned_data['username'].lower()

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')
        role = cleaned_data.get('role')
        specialite = cleaned_data.get('specialite')

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        if role == 'doctor' and not specialite:
            self.add_error('specialite', "La spécialité est obligatoire pour un médecin.")
        return cleaned_data


class PatientAccountRegisterForm(forms.ModelForm):
    """
    Formulaire médecin : créer un compte utilisateur pour un patient.
    Le rôle est forcé à 'patient' — pas de champ role dans ce formulaire.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=True, min_length=6, label="Mot de passe",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=True, label="Confirmer le mot de passe",
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'contact', 'photo']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'username':   forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'contact':    forms.TextInput(attrs={'class': 'form-control'}),
            'photo':      forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean_username(self):
        return self.cleaned_data['username'].lower()

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cleaned_data
