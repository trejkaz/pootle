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
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from pootle.core.markup import get_markup_filter_name, MarkupField
from pootle_language.models import Language
from pootle_project.models import Project
from pootle_store.models import Store, Unit


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


class VirtualFolder(models.Model):  # TODO this must be a TreeItem

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
    units = models.ManyToManyField(
        Unit,
        db_index=True,
        related_name='vfolders',
    )

    class Meta:
        unique_together = ('name', 'location')
        ordering = ['-priority', 'name']

    @cached_property
    def code(self):
        return ": ".join([self.name, self.location])

    def __unicode__(self):
        return self.code

    def save(self, *args, **kwargs):
        super(VirtualFolder, self).save(*args, **kwargs)

        # Clean any existing relationship between units and this vfolder.
        self.units.clear()

        if self.is_browsable:
            # Recreate relationships between this vfolder and units.
            for location in self.get_all_pootle_paths():
                for filename in self.filter_rules.split(","):
                    vf_file = "".join([location, filename])

                    qs = Store.objects.filter(pootle_path=vf_file)

                    if qs.exists():
                        self.units.add(*qs[0].units.all())

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

    @classmethod
    def get_matching_for(cls, pootle_path):
        """Return the matching virtual folders in the given pootle path.

        Not all the applicable virtual folders have matching filtering rules.
        This method further restricts the list of applicable virtual folders to
        retrieve only those with filtering rules that actually match.
        """
        matching = []
        for vf in cls.get_applicable_for(pootle_path):
            # Adjust virtual folder location for current pootle path.
            location = vf.get_adjusted_location(pootle_path)

            # Iterate over each file in the filtering rules to see if matches.
            for filename in vf.filter_rules.split(","):
                vf_file = "/".join([location, filename])

                if (vf_file.startswith(pootle_path) and
                    Store.objects.filter(pootle_path=vf_file).exists()):

                    matching.append(vf)
                    break

        return matching

    def get_all_pootle_paths(self):
        """Return a list with all the locations this virtual folder applies.

        If the virtual folder location has no {LANG} nor {PROJ} placeholders
        then the list only contains its location. If any of the placeholders is
        present, then they get expanded to match all the existing languages and
        projects.
        """
        if "{LANG}" in self.location and "{PROJ}" in self.location:
            locations = []
            temp = ""
            for lang in Language.objects.all():
                temp = self.location.replace("{LANG}", lang.code)
                for proj in Project.objects.all():
                    locations.append(temp.replace("{PROJ}", proj.code))
            return locations
        elif "{LANG}" in self.location:
            return [self.location.replace("{LANG}", lang.code)
                    for lang in Language.objects.all()]
        elif "{PROJ}" in self.location:
            return [self.location.replace("{PROJ}", proj.code)
                    for proj in Project.objects.all()]

        return [self.location]

    def get_adjusted_location(self, pootle_path):
        """Return the virtual folder location adjusted to the given path.

        The virtual folder location might have placeholders, which affect the
        actual filenames since those have to be concatenated to the virtual
        folder location.
        """
        count = self.location.count("/")

        if pootle_path.count("/") < count:
            raise Exception("%s is not applicable in %s" % (self, pootle_path))

        pootle_path_parts = pootle_path.strip("/").split("/")
        location_parts = self.location.strip("/").split("/")

        try:
            if (location_parts[0] != pootle_path_parts[0] and
                location_parts[0] != "{LANG}"):
                raise Exception("%s is not applicable in %s" % (self,
                                                                pootle_path))
            elif (location_parts[1] != pootle_path_parts[1] and
                  location_parts[1] != "{PROJ}"):
                raise Exception("%s is not applicable in %s" % (self,
                                                                pootle_path))
        except IndexError:
            pass

        return "/".join(pootle_path.split("/")[:count])

#    #def get_drill_down_url(self, pootle_path):
#    #    return None

#    def get_translate_url(self, pootle_path):
#        from pootle.core.url_helpers import get_editor_filter, split_pootle_path
#        lang, proj, dir, fn = split_pootle_path(pootle_path)

#        return u''.join([
#            reverse('pootle-projects-translate', args=[lang, proj, dir, fn]),
#            get_editor_filter(**kwargs),
#        ])
