# Copyright 2015 Christian Aichinger <Greek0@gmx.net>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from datetime import datetime, timedelta, timezone

import dateutil.parser
import dateutil.tz

from dateutil.relativedelta import relativedelta


class DateTime(datetime):
    """A ``datetime`` subclass with ``before()``/``after()`` methods

    Like ``datetime`` objects, it can be initialized with separate ``year``,
    ``month``, ``day``, ``hour``, ``minute``, ``second``, ``microsecond``,
    and ``tzinfo`` arguments. Additionally, it can also be constructed
    from an existing ``datetime`` instance as single argument::

        DateTime(2015, 01, 01, 15, 58, 05, 338521, timezone.utc)
        DateTime(existing_datetime_object)
    """

    def __new__(cls, *args, **kwargs):
        if not kwargs and len(args) == 1 and isinstance(args[0], datetime):
            # A single datetime argument was provided.
            dt = args[0]
            assert dt.tzinfo is not None, "DateTime objects require a timezone"

            return super().__new__(
                cls,
                dt.year, dt.month, dt.day,
                dt.hour, dt.minute, dt.second, dt.microsecond,
                dt.tzinfo)
        else:
            return super().__new__(cls, *args, **kwargs)

    def _parse_nice_date(self, when):
        """Parse a 'W years, V months, X days, Y hours, ... ago' string"""
        m = re.match(r'''\s*
                         ((?P<years>  \d+) \s+ years?   ,? \s+)?
                         ((?P<months> \d+) \s+ months?  ,? \s+)?
                         ((?P<days>   \d+) \s+ days?    ,? \s+)?
                         ((?P<hours>  \d+) \s+ hours?   ,? \s+)?
                         ((?P<minutes>\d+) \s+ minutes? ,? \s+)?
                         ((?P<seconds>\d+) \s+ seconds? ,? \s+)?
                         ago
                         \s*$
                     ''', when, re.IGNORECASE | re.VERBOSE)
        if not m:
            raise ValueError("Couldn't parse string to datetime", when)

        delta = {k: int(v)
                 for k, v in m.groupdict().items()
                 if v is not None}

        if not delta:
            raise ValueError("Date/Time string contains no date/time info",
                             when)

        return datetime.now(timezone.utc) - relativedelta(**delta)

    def after(self, when):
        """Return ``True`` if ``self`` is after ``when``"""
        return not self.before(when)

    def before(self, when):
        """Return ``True`` if ``self`` is before ``when``"""
        if isinstance(when, str):
            try:
                when = dateutil.parser.parse(when)
                if when.tzinfo is None:
                    # The user is probably talking local time.
                    when = when.replace(tzinfo=dateutil.tz.tzlocal())
            except ValueError:
                when = self._parse_nice_date(when)

        return self < when


def parse_date(datestr):
    """Parse a datetime string produced by Docker

    Return a DateTime object on success, or None on failure.

    Raises no exceptions for the expected range of inputs.
    """

    if not datestr:
        return None

    if datestr.startswith('0001-'):
        # Used by Docker as 'invalid date', e.g. for c.State.FinishedAt when
        # a container is still running.
        return None

    try:
        # Should return with tzinfo == utc.
        # No explicit tzinfo checks needed, DateTime() does that.
        dt = dateutil.parser.parse(datestr)
    except (ValueError, TypeError):
        return None

    return DateTime(dt)


