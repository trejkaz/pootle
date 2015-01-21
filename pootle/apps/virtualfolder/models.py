#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015 Zuza Software Foundation
#
# This file is part of Pootle.
#
# Pootle is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

from django.db import models
from django.utils.translation import ugettext_lazy as _

from pootle.core.markup import get_markup_filter_name, MarkupField


class VirtualFolder(models.Model):

    name = models.CharField(_('Name'), blank=False, max_length=70)
    location = models.CharField(
        _('Location'),
        blank=False,
        max_length=255,
        help_text=_('Root path where this virtual folder is applied.'),
    )
    filter_rules = models.TextField(
        # Translators: This is a noun.
        _('Filter'),
        blank=False,
        help_text=_('Filtering rules that tell which stores this virtual '
                    'folder comprises.'),
    )
    priority = models.SmallIntegerField(
        _('Priority'),
        default=1,
        help_text=_('Integer specifying importance. Greater priority means it '
                    'is more important.'),
    )
    is_browsable = models.BooleanField(
        _('Is browsable?'),
        default=False,
        help_text=_('Whether this virtual folder is active or not.'),
    )
    description = MarkupField(
        _('Description'),
        blank=True,
        help_text=_('Use this to provide more information or instructions. '
                    'Allowed markup: %s', get_markup_filter_name()),
    )

    class Meta:
        unique_together = ('name', 'location')
        ordering = ['-priority', 'name']

    def __unicode__(self):
        return ": ".join([self.name, self.location])
