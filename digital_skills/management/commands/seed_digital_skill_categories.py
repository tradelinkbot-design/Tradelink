"""
digital_skills/management/commands/seed_digital_skill_categories.py
====================================================================
Management command to seed DigitalSkillCategory and DigitalSubSkill records.

Usage:
    python manage.py seed_digital_skill_categories
    python manage.py seed_digital_skill_categories --clear   # wipe first
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from digital_skills.models import DigitalSkillCategory, DigitalSubSkill

CATEGORIES = [
    {
        'name': 'Graphic Design',
        'icon_class': 'fas fa-paint-brush',
        'description': 'Visual design for brands, marketing, and digital products.',
        'ai_context': 'expert graphic designer Nigeria branding visual identity',
        'display_order': 1,
        'sub_skills': [
            'Logo Design', 'Flyer & Poster Design', 'Brand Identity',
            'UI/UX Design', 'Social Media Graphics', 'Infographics',
            'T-Shirt & Merchandise Design', 'Business Card Design',
        ],
    },
    {
        'name': 'Web Development',
        'icon_class': 'fas fa-code',
        'description': 'Building websites, web apps, and e-commerce platforms.',
        'ai_context': 'professional web developer Nigeria frontend backend fullstack',
        'display_order': 2,
        'sub_skills': [
            'Frontend Development', 'Backend Development', 'Full-Stack Development',
            'WordPress', 'Shopify / E-Commerce', 'React / Next.js',
            'Vue.js', 'Django / Python', 'API Development',
        ],
    },
    {
        'name': 'Mobile App Development',
        'icon_class': 'fas fa-mobile-alt',
        'description': 'Native and cross-platform mobile applications.',
        'ai_context': 'mobile app developer Nigeria Android iOS Flutter',
        'display_order': 3,
        'sub_skills': [
            'Android Development', 'iOS Development', 'Flutter',
            'React Native', 'App UI Design',
        ],
    },
    {
        'name': 'Digital Marketing',
        'icon_class': 'fas fa-bullhorn',
        'description': 'Growing brands online through ads, SEO, and campaigns.',
        'ai_context': 'digital marketing specialist Nigeria SEO ads social media',
        'display_order': 4,
        'sub_skills': [
            'Search Engine Optimisation (SEO)', 'Google Ads / PPC',
            'Facebook & Instagram Ads', 'TikTok Ads',
            'Email Marketing', 'Influencer Marketing',
            'Community Management', 'Growth Hacking',
        ],
    },
    {
        'name': 'Content Writing',
        'icon_class': 'fas fa-pen-nib',
        'description': 'Written content for blogs, websites, and marketing.',
        'ai_context': 'professional content writer copywriter Nigeria blog articles',
        'display_order': 5,
        'sub_skills': [
            'Blog Writing', 'Copywriting', 'Technical Writing',
            'Script Writing', 'Product Descriptions', 'Press Releases',
            'Academic Writing', 'Proofreading & Editing',
        ],
    },
    {
        'name': 'Video & Animation',
        'icon_class': 'fas fa-film',
        'description': 'Video editing, motion graphics, and animations.',
        'ai_context': 'video editor motion graphics animation Nigeria',
        'display_order': 6,
        'sub_skills': [
            'Video Editing', '2D Animation', '3D Animation',
            'Motion Graphics', 'YouTube Video Production',
            'TikTok Content Creation', 'Corporate Video',
            'Whiteboard / Explainer Videos',
        ],
    },
    {
        'name': 'Social Media Management',
        'icon_class': 'fas fa-hashtag',
        'description': 'Managing and growing social media accounts for brands.',
        'ai_context': 'social media manager Nigeria Instagram TikTok Twitter',
        'display_order': 7,
        'sub_skills': [
            'Instagram Management', 'TikTok Management',
            'Twitter / X Management', 'Facebook Management',
            'LinkedIn Management', 'Content Calendar Planning',
            'Community Engagement',
        ],
    },
    {
        'name': 'Virtual Assistance',
        'icon_class': 'fas fa-headset',
        'description': 'Remote administrative, operational, and support tasks.',
        'ai_context': 'virtual assistant Nigeria remote support admin data entry',
        'display_order': 8,
        'sub_skills': [
            'Data Entry', 'Email Management', 'Calendar Management',
            'Customer Support', 'Research', 'Transcription',
            'CRM Management', 'E-Commerce Support',
        ],
    },
    {
        'name': 'Accounting & Finance',
        'icon_class': 'fas fa-calculator',
        'description': 'Bookkeeping, tax, payroll, and financial analysis.',
        'ai_context': 'accountant bookkeeper Nigeria finance tax payroll',
        'display_order': 9,
        'sub_skills': [
            'Bookkeeping', 'Tax Filing & Planning', 'Payroll Processing',
            'Financial Analysis', 'QuickBooks / Sage', 'Budgeting & Forecasting',
        ],
    },
    {
        'name': 'Photography',
        'icon_class': 'fas fa-camera',
        'description': 'Professional photography for products, events, and portraits.',
        'ai_context': 'photographer Nigeria product event portrait photo editing',
        'display_order': 10,
        'sub_skills': [
            'Product Photography', 'Event Photography',
            'Portrait Photography', 'Real Estate Photography',
            'Photo Editing & Retouching',
        ],
    },
    {
        'name': 'Data Science & Analytics',
        'icon_class': 'fas fa-chart-bar',
        'description': 'Data analysis, machine learning, and business intelligence.',
        'ai_context': 'data scientist analyst Nigeria Python machine learning',
        'display_order': 11,
        'sub_skills': [
            'Data Analysis', 'Machine Learning', 'Data Visualisation',
            'Business Intelligence', 'Excel / Google Sheets', 'Python / R',
            'SQL & Databases',
        ],
    },
    {
        'name': 'Cybersecurity',
        'icon_class': 'fas fa-shield-alt',
        'description': 'Protecting systems, networks, and data from cyber threats.',
        'ai_context': 'cybersecurity expert Nigeria penetration testing network security',
        'display_order': 12,
        'sub_skills': [
            'Penetration Testing', 'Network Security',
            'Security Auditing', 'Ethical Hacking',
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed DigitalSkillCategory and DigitalSubSkill records for TradeLink NG.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete existing categories and sub-skills before seeding.',
        )

    def handle(self, *args, **options):
        if options['clear']:
            DigitalSubSkill.objects.all().delete()
            DigitalSkillCategory.objects.all().delete()
            self.stdout.write(self.style.WARNING('Cleared all digital skill categories.'))

        for cat_data in CATEGORIES:
            sub_skill_names = cat_data.pop('sub_skills', [])
            slug = slugify(cat_data['name'])

            cat, created = DigitalSkillCategory.objects.update_or_create(
                slug=slug,
                defaults={**cat_data, 'slug': slug},
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(f'  {verb} category: {cat.name}')

            for ss_name in sub_skill_names:
                ss_slug = slugify(ss_name)
                ss, ss_created = DigitalSubSkill.objects.get_or_create(
                    category=cat, slug=ss_slug,
                    defaults={'name': ss_name, 'slug': ss_slug},
                )
                if ss_created:
                    self.stdout.write(f'    + {ss.name}')

        self.stdout.write(self.style.SUCCESS(
            f'\n✅  Seeded {len(CATEGORIES)} digital skill categories.'
        ))
