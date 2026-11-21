# Generated migration for digital_skills app
# Run: python manage.py migrate

import uuid
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('jobs', '0009_employerprofile_company_size_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DigitalSkillCategory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120, unique=True)),
                ('slug', models.SlugField(max_length=120, unique=True)),
                ('icon_class', models.CharField(blank=True, help_text='FontAwesome class e.g. fas fa-paint-brush', max_length=80)),
                ('description', models.TextField(blank=True)),
                ('ai_context', models.TextField(blank=True, help_text="Natural-language context for embedding (e.g. 'expert graphic designer Nigeria').")),
                ('display_order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Digital Skill Category',
                'verbose_name_plural': 'Digital Skill Categories',
                'ordering': ['display_order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='DigitalSubSkill',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('slug', models.SlugField(max_length=120)),
                ('is_active', models.BooleanField(default=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sub_skills', to='digital_skills.digitalskillcategory')),
            ],
            options={
                'ordering': ['category', 'name'],
                'unique_together': {('category', 'slug')},
            },
        ),
        migrations.CreateModel(
            name='DigitalWorkerProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('headline', models.CharField(blank=True, help_text='One-line professional headline shown on the directory card, e.g. "Expert React Developer | 5 yrs exp"', max_length=200)),
                ('bio', models.TextField(blank=True, help_text='Full profile bio — primary text encoded by the AI matcher.')),
                ('experience_level', models.CharField(choices=[('entry', 'Entry (0–2 years)'), ('mid', 'Intermediate (3–5 years)'), ('experienced', 'Experienced (6–10 years)'), ('expert', 'Expert (10+ years)')], default='entry', max_length=20)),
                ('years_experience', models.PositiveSmallIntegerField(default=0)),
                ('hourly_rate', models.DecimalField(blank=True, decimal_places=2, help_text='Hourly rate in NGN', max_digits=10, null=True)),
                ('project_rate', models.DecimalField(blank=True, decimal_places=2, help_text='Starting fixed price per project in NGN', max_digits=10, null=True)),
                ('state', models.CharField(blank=True, choices=[('abia', 'Abia'), ('adamawa', 'Adamawa'), ('akwa_ibom', 'Akwa Ibom'), ('anambra', 'Anambra'), ('bauchi', 'Bauchi'), ('bayelsa', 'Bayelsa'), ('benue', 'Benue'), ('borno', 'Borno'), ('cross_river', 'Cross River'), ('delta', 'Delta'), ('ebonyi', 'Ebonyi'), ('edo', 'Edo'), ('ekiti', 'Ekiti'), ('enugu', 'Enugu'), ('fct', 'FCT – Abuja'), ('gombe', 'Gombe'), ('imo', 'Imo'), ('jigawa', 'Jigawa'), ('kaduna', 'Kaduna'), ('kano', 'Kano'), ('katsina', 'Katsina'), ('kebbi', 'Kebbi'), ('kogi', 'Kogi'), ('kwara', 'Kwara'), ('lagos', 'Lagos'), ('nasarawa', 'Nasarawa'), ('niger', 'Niger'), ('ogun', 'Ogun'), ('ondo', 'Ondo'), ('osun', 'Osun'), ('oyo', 'Oyo'), ('plateau', 'Plateau'), ('rivers', 'Rivers'), ('sokoto', 'Sokoto'), ('taraba', 'Taraba'), ('yobe', 'Yobe'), ('zamfara', 'Zamfara')], max_length=40)),
                ('lga', models.CharField(blank=True, max_length=120, verbose_name='Local Government Area')),
                ('remote_ok', models.BooleanField(default=True, help_text='Can work fully remotely.')),
                ('availability', models.CharField(choices=[('available', 'Available Now'), ('soon', 'Available Soon'), ('busy', 'Currently Busy'), ('unavailable', 'Not Available')], default='available', max_length=20)),
                ('employment_preference', models.CharField(choices=[('full_time', 'Full-Time Employment'), ('part_time', 'Part-Time Employment'), ('either', 'Either Full or Part-Time'), ('gig_only', 'Gig / Contract Work Only')], default='gig_only', max_length=20)),
                ('open_to_employment', models.BooleanField(default=False, help_text='Shows an "Open to Work" badge on the directory listing.')),
                ('expected_monthly_salary', models.DecimalField(blank=True, decimal_places=2, help_text='Expected monthly salary in NGN if seeking full-time employment.', max_digits=12, null=True)),
                ('notice_period', models.CharField(blank=True, help_text='e.g. "Available immediately", "2 weeks notice".', max_length=100)),
                ('whatsapp_number', models.CharField(blank=True, help_text='WhatsApp number for direct contact (shown to verified employers).', max_length=20)),
                ('portfolio_url', models.URLField(blank=True, help_text='External portfolio / Behance / GitHub')),
                ('linkedin_url', models.URLField(blank=True)),
                ('twitter_url', models.URLField(blank=True)),
                ('is_verified', models.BooleanField(default=False, help_text='Admin-granted verified badge (blue checkmark).')),
                ('is_featured', models.BooleanField(default=False, help_text='Featured workers appear at the top of search results.')),
                ('profile_completion', models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(100)])),
                ('text_embedding', models.JSONField(blank=True, help_text='Sentence-transformer embedding. 768-dim float list. Recomputed when headline, bio, or skills change.', null=True)),
                ('text_embedding_updated', models.DateTimeField(blank=True, null=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('primary_category', models.ForeignKey(blank=True, help_text='The main discipline this worker identifies with.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='primary_workers', to='digital_skills.digitalskillcategory')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='digital_worker_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Digital Worker Profile',
                'verbose_name_plural': 'Digital Worker Profiles',
            },
        ),
        migrations.CreateModel(
            name='DigitalWorkerSubSkill',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('years_exp', models.PositiveSmallIntegerField(default=0)),
                ('sub_skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='digital_skills.digitalsubskill')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='digital_skills.digitalworkerprofile')),
            ],
            options={
                'unique_together': {('worker', 'sub_skill')},
            },
        ),
        migrations.AddField(
            model_name='digitalworkerprofile',
            name='sub_skills',
            field=models.ManyToManyField(blank=True, related_name='workers', through='digital_skills.DigitalWorkerSubSkill', to='digital_skills.DigitalSubSkill'),
        ),
        migrations.CreateModel(
            name='DigitalPortfolioItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('item_type', models.CharField(choices=[('image', 'Image Upload'), ('link', 'External Link'), ('video', 'Video Link (YouTube / Vimeo)')], default='image', max_length=10)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='digital_portfolio/')),
                ('external_url', models.URLField(blank=True, help_text='URL for LINK or VIDEO items.')),
                ('display_order', models.PositiveSmallIntegerField(default=0)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='portfolio_items', to='digital_skills.digitalworkerprofile')),
            ],
            options={
                'verbose_name': 'Digital Portfolio Item',
                'verbose_name_plural': 'Digital Portfolio Items',
                'ordering': ['display_order', '-created'],
            },
        ),
        migrations.CreateModel(
            name='DigitalGig',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('budget_type', models.CharField(choices=[('fixed', 'Fixed Price'), ('hourly', 'Per Hour')], default='fixed', max_length=10)),
                ('budget_min', models.DecimalField(blank=True, decimal_places=2, help_text='Minimum budget in NGN.', max_digits=12, null=True)),
                ('budget_max', models.DecimalField(blank=True, decimal_places=2, help_text='Maximum budget in NGN.', max_digits=12, null=True)),
                ('work_type', models.CharField(choices=[('remote', 'Fully Remote'), ('onsite', 'On-Site'), ('hybrid', 'Hybrid')], default='remote', max_length=10)),
                ('state', models.CharField(blank=True, choices=[('abia', 'Abia'), ('adamawa', 'Adamawa'), ('akwa_ibom', 'Akwa Ibom'), ('anambra', 'Anambra'), ('bauchi', 'Bauchi'), ('bayelsa', 'Bayelsa'), ('benue', 'Benue'), ('borno', 'Borno'), ('cross_river', 'Cross River'), ('delta', 'Delta'), ('ebonyi', 'Ebonyi'), ('edo', 'Edo'), ('ekiti', 'Ekiti'), ('enugu', 'Enugu'), ('fct', 'FCT – Abuja'), ('gombe', 'Gombe'), ('imo', 'Imo'), ('jigawa', 'Jigawa'), ('kaduna', 'Kaduna'), ('kano', 'Kano'), ('katsina', 'Katsina'), ('kebbi', 'Kebbi'), ('kogi', 'Kogi'), ('kwara', 'Kwara'), ('lagos', 'Lagos'), ('nasarawa', 'Nasarawa'), ('niger', 'Niger'), ('ogun', 'Ogun'), ('ondo', 'Ondo'), ('osun', 'Osun'), ('oyo', 'Oyo'), ('plateau', 'Plateau'), ('rivers', 'Rivers'), ('sokoto', 'Sokoto'), ('taraba', 'Taraba'), ('yobe', 'Yobe'), ('zamfara', 'Zamfara')], max_length=40)),
                ('deadline', models.DateField(blank=True, help_text='Application or project deadline.', null=True)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('active', 'Active'), ('paused', 'Paused'), ('closed', 'Closed'), ('filled', 'Filled')], db_index=True, default='draft', max_length=10)),
                ('text_embedding', models.JSONField(blank=True, null=True)),
                ('text_embedding_updated', models.DateTimeField(blank=True, null=True)),
                ('views_count', models.PositiveIntegerField(default=0, editable=False)),
                ('applications_count', models.PositiveIntegerField(default=0, editable=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gigs', to='digital_skills.digitalskillcategory')),
                ('employer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='digital_gigs', to='jobs.employerprofile')),
                ('required_sub_skills', models.ManyToManyField(blank=True, related_name='gigs', to='digital_skills.DigitalSubSkill')),
            ],
            options={
                'verbose_name': 'Digital Gig',
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='DigitalApplication',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('cover_note', models.TextField(blank=True, help_text='Short pitch — why you are the best person for this gig.')),
                ('proposed_rate', models.DecimalField(blank=True, decimal_places=2, help_text='Your proposed fixed price or hourly rate in NGN.', max_digits=12, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending Review'), ('shortlisted', 'Shortlisted'), ('rejected', 'Rejected'), ('hired', 'Hired')], db_index=True, default='pending', max_length=15)),
                ('employer_note', models.TextField(blank=True, help_text='Private employer feedback on this application.')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('gig', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='applications', to='digital_skills.digitalgig')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='applications', to='digital_skills.digitalworkerprofile')),
            ],
            options={
                'verbose_name': 'Digital Application',
                'ordering': ['-created'],
                'unique_together': {('gig', 'worker')},
            },
        ),
        migrations.CreateModel(
            name='SavedDigitalGig',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('gig', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_by', to='digital_skills.digitalgig')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_digital_gigs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Saved Digital Gig',
                'unique_together': {('user', 'gig')},
            },
        ),
        migrations.CreateModel(
            name='DigitalWorkerReview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('rating', models.PositiveSmallIntegerField(choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')], help_text='1–5 stars.')),
                ('comment', models.TextField(blank=True)),
                ('is_public', models.BooleanField(default=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('gig', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviews', to='digital_skills.digitalgig')),
                ('reviewer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='digital_reviews_given', to=settings.AUTH_USER_MODEL)),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='digital_skills.digitalworkerprofile')),
            ],
            options={
                'verbose_name': 'Digital Worker Review',
                'ordering': ['-created'],
                'unique_together': {('worker', 'reviewer', 'gig')},
            },
        ),
    ]
