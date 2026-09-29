"""
jobs/migrations/0002_hybrid_scoring_fields.py
==============================================
Adds:
  WorkerProfile.text_embedding            — sentence-transformer 768-dim
  WorkerProfile.text_embedding_updated    — timestamp
  Job.text_embedding                      — sentence-transformer 768-dim
  Job.text_embedding_updated              — timestamp
  CLIPMatch.text_score                    — component score
  CLIPMatch.image_score                   — component score
  CLIPMatch.location_score                — component score
  CLIPMatch.experience_score              — component score
  CLIPMatch.rating_score                  — component score
  CLIPMatch.verification_bonus            — component score

All new fields are nullable so the migration is non-destructive and can be
applied with zero downtime on an existing database.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
    ]

    operations = [

        # ── WorkerProfile ────────────────────────────────────────────────────
        migrations.AddField(
            model_name='workerprofile',
            name='text_embedding',
            field=models.JSONField(
                blank=True, null=True,
                help_text='Sentence-transformer embedding (768-dim). '
                          'Recomputed when profile text changes.',
            ),
        ),
        migrations.AddField(
            model_name='workerprofile',
            name='text_embedding_updated',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── Job ───────────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='job',
            name='text_embedding',
            field=models.JSONField(
                blank=True, null=True,
                help_text='Sentence-transformer embedding (768-dim). '
                          'Recomputed when job text changes.',
            ),
        ),
        migrations.AddField(
            model_name='job',
            name='text_embedding_updated',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── CLIPMatch component scores ────────────────────────────────────────
        migrations.AddField(
            model_name='clipmatch',
            name='text_score',
            field=models.FloatField(
                blank=True, null=True,
                help_text='Sentence-transformer cosine similarity (0–1).',
            ),
        ),
        migrations.AddField(
            model_name='clipmatch',
            name='image_score',
            field=models.FloatField(
                blank=True, null=True,
                help_text='CLIP image↔text similarity avg across portfolio items (0–1).',
            ),
        ),
        migrations.AddField(
            model_name='clipmatch',
            name='location_score',
            field=models.FloatField(
                blank=True, null=True,
                help_text='1.0=same state, 0.5=willing to relocate/remote, 0.0=mismatch.',
            ),
        ),
        migrations.AddField(
            model_name='clipmatch',
            name='experience_score',
            field=models.FloatField(
                blank=True, null=True,
                help_text='How well worker experience level fits the job type (0–1).',
            ),
        ),
        migrations.AddField(
            model_name='clipmatch',
            name='rating_score',
            field=models.FloatField(
                blank=True, null=True,
                help_text='Normalised average worker rating: (avg-1)/4. Default 0.5.',
            ),
        ),
        migrations.AddField(
            model_name='clipmatch',
            name='verification_bonus',
            field=models.FloatField(
                blank=True, null=True,
                help_text='1.0 if worker is admin-verified, 0.0 otherwise.',
            ),
        ),

        # Update score field help_text to reflect hybrid nature
        migrations.AlterField(
            model_name='clipmatch',
            name='score',
            field=models.FloatField(
                help_text='Weighted hybrid score: 50% text + 15% location + '
                          '15% experience + 10% image + 5% rating + 5% verification.',
            ),
        ),
    ]