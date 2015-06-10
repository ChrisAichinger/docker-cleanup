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

from datetime import datetime, timedelta, timezone

from dateutil.tz import tzutc

import pytest

from docker_cleanup import dates

date_time_pairs = [
    ('2001-01-31T13:05:20.123456Z',     datetime(2001, 1, 31, 13, 5, 20, 123456, tzutc())),
    ('2001-01-31T13:05:20.1234567890Z', datetime(2001, 1, 31, 13, 5, 20, 123456, tzutc())),
    ('2001-01-31T13:05:20.1234Z',       datetime(2001, 1, 31, 13, 5, 20, 123400, tzutc())),
    ('', None),
    ('nonsense', None),
    ('0001-01-01T00:00:00Z', None),   # Used by docker as 'invalid date'
]


def test_DateTime_creation():
    input = expected = datetime(2001, 1, 31, 13, 5, 20, 123456, tzutc())

    dt1 = dates.DateTime(input)
    dt2 = dates.DateTime(
        input.year, input.month, input.day,
        input.hour, input.minute, input.second, input.microsecond,
        input.tzinfo)

    assert dt1 == expected
    assert dt2 == expected


@pytest.mark.parametrize("input,expected", date_time_pairs)
def test_parse_date(input, expected):
    assert dates.parse_date(input) == expected


def test_parse_date_cornercases():
    assert dates.parse_date('is no date') is None


@pytest.fixture(params=['from-datetime', 'from-iso8601'])
def datetime_7d_past(request):
    if request.param == 'from-datetime':
        return dates.DateTime(datetime.now(timezone.utc) - timedelta(days=7))

    if request.param == 'from-iso8601':
        # Do not supply tzinfo here, otherwise isoformat() appends '+00:00'.
        dt = datetime.utcnow() - timedelta(days=7)
        return dates.parse_date(dt.isoformat() + 'Z')
    raise NotImplementedError('Unknown fixture parameter', request.param)

datetime_input_before = [
        ('2038-1-1', True),
        ('January 1, 2038', True),
        ('6 days, 23 hours ago', True),

        ('2015-05-15', False),
        ('May 15, 2015', False),
        ('7 days, 1 hour ago', False),
        ('1 month ago', False),
        ('2 months ago', False),
        ('1 year ago', False),
        ('2 years ago', False),
        ]

datetime_input_invalid = set(['ago', '2500 turtles', '6 apples ago', '   ago'])

def test_DateTime_before_after(datetime_7d_past):
    now = datetime.now(timezone.utc)

    assert datetime_7d_past.before(now)
    assert datetime_7d_past.before(now - timedelta(days=6, hours=23))
    assert not datetime_7d_past.before(now - timedelta(days=7, hours=1))

@pytest.mark.parametrize("input,expected", datetime_input_before)
def test_DateTime_before_after_str(input, expected, datetime_7d_past):
    assert datetime_7d_past.before(input) == expected
    assert datetime_7d_past.after(input) != expected

@pytest.mark.parametrize("input", datetime_input_invalid)
def test_DateTime_before_after_invalid(input, datetime_7d_past):
    with pytest.raises(ValueError):
        datetime_7d_past.before(input)
    with pytest.raises(ValueError):
        datetime_7d_past.after(input)


