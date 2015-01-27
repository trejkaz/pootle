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

import re

from django.db import models
from django.utils.translation import ugettext_lazy as _

from pootle.core.markup import get_markup_filter_name, MarkupField


def pattern_for_path(pootle_path):
    """Return a regular expression to match Virtual Folders locations.

    Given a pootle path like /gl/firefox/browser/chrome/ this function returns
    a regular expression to filter all the existing virtual folders to only
    retrieve the ones that are applicable in that pootle path.

    For the pootle path specified above the applicable virtual folders are the
    ones with locations matching the provided pootle path, and also the pootle
    path for any upper directory. Also it matches any location that includes
    the {LANG} or {PROJ} placeholders in any combination. Those virtual folders
    whose location starts with /projects/ and have the same path are also
    returned.
    """
    def pattern_for_sublist(sublist):
        if len(sublist) == 1:
            return "".join([
                "(/",
                sublist[0],
                ")?",
            ])

        return "".join([
            "(/",
            sublist[0],
            pattern_for_sublist(sublist[1:]),
            ")?",
        ])

    items = pootle_path.strip("/").split("/")
    str_list = [
        "^/((",
        items[0],
        "|\{LANG\}|projects)",
    ]

    if len(items) > 1:
        str_list += [
            "|((",
            items[0],
            "|\{LANG\}|projects)(/(",
            items[1],
            "|{PROJ})",
        ]

        if len(items) > 2:
            str_list += pattern_for_sublist(items[2:])

        str_list.append(")?)")

    str_list.append(")/$")

    return "".join(str_list)


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

    @classmethod
    def get_applicable_for(cls, pootle_path):
        """Return the applicable virtual folders in the given pootle path.

        Given a pootle path like /gl/firefox/browser/chrome/ this method
        returns the virtual folders whose location matches.

        For the pootle path specified above the applicable virtual folders are
        the ones with locations matching the provided pootle path, and also the
        pootle path for any upper directory. Also it matches any location that
        includes the {LANG} or {PROJ} placeholders in any combination. Those
        virtual folders whose location starts with /projects/ and have the same
        path are also returned.
        """
        vf_re = re.compile(pattern_for_path(pootle_path))

        #TODO consider passing the regex directly to the ORM. See
        # https://docs.djangoproject.com/en/1.7/ref/models/querysets/#regex
        return [vf for vf in VirtualFolder.objects.filter(is_browsable=True)
                if vf_re.match(vf.location)]
