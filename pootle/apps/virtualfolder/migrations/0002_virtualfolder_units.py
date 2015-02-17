# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pootle_store', '0001_initial'),
        ('virtualfolder', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='virtualfolder',
            name='units',
            field=models.ManyToManyField(related_name='vfolders', to='pootle_store.Unit', db_index=True),
            preserve_default=True,
        ),
    ]
