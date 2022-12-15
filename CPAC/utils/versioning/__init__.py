# Copyright (C) 2022  C-PAC Developers

# This file is part of C-PAC.

# C-PAC is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.

# C-PAC is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with C-PAC. If not, see <https://www.gnu.org/licenses/>.
"""Gather and report dependency versions alphabetically"""
import sys
from pkg_resources import working_set

PYTHON_PACKAGES = dict(sorted({
  d.key: d.version for d in list(working_set)}.items()))
REPORTED = dict(sorted({
  'Python': sys.version.replace('\n', ' ').replace('  ', ' ')
}.items()))

__all__ = ['PYTHON_PACKAGES', 'REPORTED']