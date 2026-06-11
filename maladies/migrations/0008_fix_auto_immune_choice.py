# Correction du choix 'auto-immune ' (espace parasite) -> 'auto-immune'.
from django.db import migrations, models


def fix_auto_immune_data(apps, schema_editor):
    """Met à jour les enregistrements existants dont type='auto-immune ' (avec espace)."""
    Maladie = apps.get_model('maladies', 'Maladie')
    Maladie.objects.filter(type='auto-immune ').update(type='auto-immune')


def reverse_auto_immune_data(apps, schema_editor):
    Maladie = apps.get_model('maladies', 'Maladie')
    Maladie.objects.filter(type='auto-immune').update(type='auto-immune ')


class Migration(migrations.Migration):

    dependencies = [
        ('maladies', '0007_alter_patientmaladie_options_and_more'),
    ]

    operations = [
        migrations.RunPython(fix_auto_immune_data, reverse_auto_immune_data),
        migrations.AlterField(
            model_name='maladie',
            name='type',
            field=models.CharField(
                choices=[
                    ('infectieuse', 'Infectieuse'),
                    ('metabolique', 'Métabolique'),
                    ('respiratoire', 'Respiratoire'),
                    ('cardiovasculaire', 'cardiovasculaire'),
                    ('neurologique', 'Neurologique'),
                    ('auto-immune', 'auto-immune'),
                    ('rénale', 'rénale'),
                    ('autre', 'Autre'),
                ],
                default='autre',
                max_length=20,
            ),
        ),
    ]
