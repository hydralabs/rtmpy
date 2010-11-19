# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.


import os.path

from docutils.core import publish_parts


def rst2html( input, output ):
    """
    Create html file from rst file.

    :param input: Path to rst source file
    :type: `str`
    :param output: Path to html output file
    :type: `str`
    """
    file = os.path.abspath(input)
    rst = open(file, 'r').read()
    html = publish_parts(rst, writer_name='html')
    body = html['html_body']

    tmp = open(output, 'w')
    tmp.write(body)
    tmp.close()

    return body

