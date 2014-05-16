#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2014 Evernote Corporation
#
# This file is part of Pootle.
#
# Pootle is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Pootle is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pootle; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


__all__ = ('User', )


import datetime
import re
from hashlib import md5

from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from pootle.core.cache import make_method_key
from pootle.managers import UserManager
from pootle_language.models import Language
from pootle_statistics.models import Submission, SubmissionTypes
from pootle_store.models import SuggestionStates
from pootle_translationproject.models import TranslationProject


def _humanize_score(score):
    """Returns a human-readable score for public display."""
    return int(round(score))


class User(AbstractBaseUser):
    """The Pootle User.

    ``username``, ``password`` and ``email`` are required. Other fields
    are optional.

    Note that the ``password`` and ``last_login`` fields are inherited
    from ``AbstractBaseUser``.
    """
    username = models.CharField(_('username'), max_length=30, unique=True,
        help_text=_('Required. 30 characters or fewer. Letters, numbers and '
                    '@/./+/-/_ characters'),
        validators=[
            RegexValidator(re.compile('^[\w.@+-]+$'),
                           _('Enter a valid username.'),
                           'invalid')
        ],
    )
    email = models.EmailField(_('email address'), max_length=255)
    full_name = models.CharField(_('Full name'), max_length=255, blank=True)

    is_active = models.BooleanField(_('active'), default=True,
        help_text=_('Designates whether this user should be treated as '
                    'active. Unselect this instead of deleting accounts.'))
    is_superuser = models.BooleanField(_('superuser status'), default=False,
        help_text=_('Designates that this user has all permissions without '
                    'explicitly assigning them.'))

    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    # Translation setting fields
    unit_rows = models.SmallIntegerField(default=9,
            verbose_name=_("Number of Rows"))
    alt_src_langs = models.ManyToManyField('pootle_language.Language',
            blank=True, db_index=True, limit_choices_to=~Q(code='templates'),
            verbose_name=_("Alternative Source Languages"))

    # Score-related fields
    rate = models.FloatField(null=False, default=0)
    review_rate = models.FloatField(null=False, default=0)
    score = models.FloatField(null=False, default=0)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    objects = UserManager()

    class Meta:
        app_label = 'pootle'

    @property
    def display_name(self):
        """Human-readable display name."""
        return (self.get_full_name() if self.get_full_name()
                                     else self.get_short_name())

    @property
    def public_score(self):
        return _humanize_score(self.score)

    @property
    def public_total_score(self):
        """Total score for a specific period.

        Since `total_score` is not an attribute of the `User` model, this
        should be used with user objects retrieved via `User.top_scorers()`.
        """
        return _humanize_score(getattr(self, 'total_score', self.score))

    @cached_property
    def email_hash(self):
        try:
            return md5(self.email).hexdigest()
        except UnicodeEncodeError:
            return None

    @classmethod
    def get(cls, user):
        """Return the expected user instance.

        This function is only necessary if `user` could be anonymous,
        because we want to work with the instance of the special `nobody`
        user instead of Django's own `AnonymousUser`.

        If you know for certain that a user is logged in, then use it
        straight away.
        """
        if user.is_authenticated():
            return user

        return cls.objects.get_nobody_user()

    @classmethod
    def top_scorers(cls, days=30, language=None, project=None, limit=5):
        """Returns users with the top scores.

        :param days: period of days to account for scores.
        :param language: limit results to the given language code.
        :param project: limit results to the given project code.
        :param limit: limit results to this number of users.
        """
        cache_kwargs = {
            'days': days,
            'language': language,
            'project': project,
            'limit': limit,
        }
        cache_key = make_method_key(cls, 'top_scorers', cache_kwargs)

        top_scorers = cache.get(cache_key, None)
        if top_scorers is not None:
            return top_scorers

        now = datetime.datetime.now()
        past = now + datetime.timedelta(-days)

        lookup_kwargs = {
            'scorelog__creation_time__range': [past, now],
        }

        if language is not None:
            lookup_kwargs.update({
                'scorelog__submission__translation_project__language__code':
                    language,
            })

        if project is not None:
            lookup_kwargs.update({
                'scorelog__submission__translation_project__project__code':
                    project,
            })

        top_scorers = cls.objects.hide_defaults().filter(
            **lookup_kwargs
        ).annotate(
            total_score=Sum('scorelog__score_delta'),
        ).filter(total_score__gt=0.0).order_by('-total_score')[:limit]

        cache.set(cache_key, top_scorers, 60)
        return top_scorers

    def __unicode__(self):
        return self.username

    def get_absolute_url(self):
        return reverse('pootle-profile', args=[self.username])

    def get_full_name(self):
        """Returns the user's full name."""
        return self.full_name.strip()

    def get_short_name(self):
        """Returns the short name for the user."""
        return self.username

    def email_user(self, subject, message, from_email=None):
        """Sends an email to this user."""
        send_mail(subject, message, from_email, [self.email])

    def gravatar_url(self, size=80):
        if not self.email_hash:
            return ''

        return 'https://secure.gravatar.com/avatar/%s?s=%d&d=mm' % \
            (self.email_hash, size)

    def get_unit_rows(self):
        return min(max(self.unit_rows, 5), 49)

    def pending_suggestion_count(self, tp):
        """Returns the number of pending suggestions for the user in the given
        translation project.

        :param tp: a :cls:`TranslationProject` object.
        """
        return self.suggestions.filter(unit__store__translation_project=tp,
                                       state=SuggestionStates.PENDING).count()

    def accepted_suggestion_count(self, tp):
        """Returns the number of accepted suggestions for the user in the given
        translation project.

        :param tp: a :cls:`TranslationProject` object.
        """
        return self.suggestions.filter(unit__store__translation_project=tp,
                                       state=SuggestionStates.ACCEPTED).count()

    def rejected_suggestion_count(self, tp):
        """Returns the number of rejected suggestions for the user in the given
        translation project.

        :param tp: a :cls:`TranslationProject` object.
        """
        return self.suggestions.filter(unit__store__translation_project=tp,
                                       state=SuggestionStates.REJECTED).count()

    def total_submission_count(self, tp):
        """Returns the number of submissions the current user has done from the
        editor in the given translation project.

        :param tp: a :cls:`TranslationProject` object.
        """
        return Submission.objects.filter(
            submitter=self,
            translation_project=tp,
            type=SubmissionTypes.NORMAL,
        ).count()

    def overwritten_submission_count(self, tp):
        """Returns the number of submissions the current user has done from the
        editor and have been overwritten by other users in the given
        translation project.

        :param tp: a :cls:`TranslationProject` object.
        """
        return Submission.objects.filter(
            submitter=self,
            translation_project=tp,
            type=SubmissionTypes.NORMAL,
        ).exclude(
            unit__submitted_by=self,
        ).count()

    @property
    def contributions(self):
        """Get user contributions grouped by language and project.

        :return: List of tuples containing the following information::

            [
              ('Language 1', [
                  ('Project 1', [
                      {
                        'id': 'foo-bar',
                        'count': 0,
                        'url': 'foo/bar',
                      },
                      {
                        'id': 'bar-foo',
                        'count': 3,
                        'url': 'baz/blah',
                      },
                      {
                        'id': 'baz-blah',
                        'count': 5,
                        'url': 'bar/baz',
                      },
                  ]),
                  ('Project 2', [
                      ...
                  ]),
              ]),
              ('LanguageN', [
                  ('Project N', [
                      ...
                  ]),
                  ('Project N+1', [
                      ...
                  ]),
              ]),
            ]
        """
        # TODO: optimize — we need a schema that helps reduce the number
        # of needed queries for these kind of data retrievals
        contributions = []
        username = self.username
        edit_types = [
            SubmissionTypes.NORMAL,
            SubmissionTypes.SUGG_ADD,
            SubmissionTypes.SYSTEM,
        ]
        languages = Language.objects.filter(
            translationproject__submission__submitter=self,
            translationproject__submission__type__in=edit_types,
        ).distinct()

        for language in languages:
            translation_projects = TranslationProject.objects.filter(
                language=language,
                submission__submitter=self,
                submission__type__in=edit_types,
            ).distinct().order_by('project__fullname')

            tp_user_stats = []
            # Retrieve tp-specific stats for this user
            for tp in translation_projects:
                tp_stats = [
                    {
                        'id': 'suggestions-pending',
                        'count': self.pending_suggestion_count(tp),
                        'url': tp.get_translate_url(state='user-suggestions',
                                                    user=username),
                    },
                    {
                        'id': 'suggestions-accepted',
                        'count': self.accepted_suggestion_count(tp),
                        'url': tp.get_translate_url(
                            state='user-suggestions-accepted',
                            user=username,
                        ),
                    },
                    {
                        'id': 'suggestions-rejected',
                        'count': self.rejected_suggestion_count(tp),
                        'url': tp.get_translate_url(
                            state='user-suggestions-rejected',
                            user=username,
                        ),
                    },
                    {
                        'id': 'submissions-total',
                        'count': self.total_submission_count(tp),
                        'url': tp.get_translate_url(state='user-submissions',
                                                    user=username),
                    },
                    {
                        'id': 'submissions-overwritten',
                        'count': self.overwritten_submission_count(tp),
                        'url': tp.get_translate_url(
                            state='user-submissions-overwritten',
                            user=username,
                        ),
                    },
                ]

                tp_user_stats.append((tp, tp_stats))

            contributions.append((language, tp_user_stats))

        return contributions