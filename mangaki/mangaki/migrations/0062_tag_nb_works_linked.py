# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-07-24 14:38
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mangaki', '0061_auto_20160724_1351'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='nb_works_linked',
            field=models.IntegerField(default=0),
        ),
    ]