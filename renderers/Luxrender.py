# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2017 Yorik van Havre <yorik@uncreated.net>              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

"""Luxrender renderer for FreeCAD"""

# This file can also be used as a template to add more rendering engines.
# You will need to make sure your file is named with a same name (case
# sensitive)
# That you will use everywhere to describe your renderer, ex: Appleseed or
# Povray


# A render engine module must contain the following functions:
#
# write_camera(pos, rot, up, target)
#   returns a string containing an openInventor camera string in renderer
#   format
#
# write_object(view, mesh, color, alpha)
#   returns a string containing a RaytracingView object in renderer format
#
# render(project, prefix, external, output, width, height)
#   renders the given project
#   external means if the user wishes to open the render file in an external
#   application/editor or not. If this is not supported by your renderer, you
#   can simply ignore it
#
# Additionally, you might need/want to add:
#   Preference page items, that can be used in your functions below
#   An icon under the name Renderer.svg (where Renderer is the name of your
#   Renderer


import os
import re
import shlex
from tempfile import mkstemp
from subprocess import Popen
from textwrap import dedent

import FreeCAD as App


def write_camera(pos, rot, updir, target, name):
    """Compute a string in the format of Luxrender, that represents a camera"""
    # This is where you create a piece of text in the format of
    # your renderer, that represents the camera.

    up = updir
    pos = str(pos.x) + " " + str(pos.y) + " " + str(pos.z)
    target = str(target.x) + " " + str(target.y) + " " + str(target.z)
    up = str(up.x) + " " + str(up.y) + " " + str(up.z)

    cam  = "# declares position and view direction\n"
    cam += "# Generated by FreeCAD (http://www.freecadweb.org/)\n"
    cam += "LookAt " + pos + " "
    cam += target + " "
    cam += up + "\n"
    return cam


def write_object(viewobj, mesh, color, alpha):
    """Compute a string in the format of Luxrender, that represents a FreeCAD
    object
    """
    # This is where you write your object/view in the format of your
    # renderer. "obj" is the real 3D object handled by this project, not
    # the project itself. This is your only opportunity
    # to write all the data needed by your object (geometry, materials, etc)
    # so make sure you include everything that is needed


    objname = viewobj.Name

    # format color
    color = "{} {} {}".format(*color)

    # get geometry
    P = ["{} {} {}".format(v.x, v.y, v.z) for v in mesh.Topology[0]]
    P = " ".join(P)
    N = ["{} {} {}".format(n.x, n.y, n.z) for n in mesh.getPointNormals()]
    N = " ".join(N)
    tris = ["{} {} {}".format(*t) for t in mesh.Topology[1]]
    tris = " ".join(tris)

    objdef = list()

    # write shader
    objdef.append('MakeNamedMaterial "{}_mat"'.format(objname))
    objdef.append('    "color Kd"       [{}]'.format(color))
    objdef.append('    "float sigma"    [0.2]')
    objdef.append('    "string type"    ["matte"]')
    if alpha < 1.0:
        objdef.append('    "float transparency" ["{}"]'.format(alpha))
    objdef.append('\n')

    # write mesh
    objdef.append('AttributeBegin # "{}"'.format(objname))
    objdef.append('Transform [1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1]')
    objdef.append('NamedMaterial "{}_mat"'.format(objname))
    objdef.append('Shape "mesh"')
    objdef.append('    "integer triindices" [{}]'.format(tris))
    objdef.append('    "point P" [{}]'.format(P))
    objdef.append('    "normal N" [{}]'.format(N))
    objdef.append('    "bool generatetangents" ["false"]')
    objdef.append('    "string name" ["{}"]'.format(objname))
    objdef.append('AttributeEnd # "{}_mat"'.format(objname))
    objdef.append('\n')

    return "\n".join(objdef)




def write_pointlight(view, location, color, power):
    """Compute a string in the format of Luxrender, that represents a
    PointLight object
    """
    # This is where you write the renderer-specific code
    # to export the point light in the renderer format

    # From Luxcore doc:
    # power is in watts
    # efficency (sic) is in lumens/watt
    efficency = 15 # incandescent light bulb ratio (average)
    gain = 10 # Guesstimated! (don't hesitate to propose a more sensible value)

    objdef = list()
    objdef.append('AttributeBegin # "{}"'.format(view.Name))
    objdef.append('Transform [1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1]')
    objdef.append('LightSource "point"')
    objdef.append('     "float from"        [{:.9f} {:.9f} {:.9f}]'.format(*location))
    objdef.append('     "color L"           [{:.9f} {:.9f} {:.9f}]'.format(*color))
    objdef.append('     "float power"       [{:.9f}]'.format(power))
    objdef.append('     "float efficency"   [{:.9f}]'.format(efficency))
    objdef.append('     "float gain"        [{:.9f}]'.format(gain))
    objdef.append('AttributeEnd # "{}"'.format(view.Name))
    objdef.append('\n')

    return "\n".join(objdef)


def render(project, prefix, external, output, width, height):
    """Run Luxrender

    Params:
    - project:  the project to render
    - prefix:   a prefix string for call (will be inserted before path to Lux)
    - external: a boolean indicating whether to call UI (true) or console
                (false) version of Lux
    - width:    rendered image width, in pixels
    - height:   rendered image height, in pixels

    Return: void
    """
    # Here you trigger a render by firing the renderer
    # executable and passing it the needed arguments, and
    # the file it needs to render

    # change image size in template
    f = open(project.PageResult,"r")
    t = f.read()
    f.close()
    res = re.findall("integer xresolution",t)
    if res:
        t = re.sub("\"integer xresolution\".*?\[.*?\]","\"integer xresolution\" ["+str(width)+"]",t)
    res = re.findall("integer yresolution",t)
    if res:
        t = re.sub("\"integer yresolution\".*?\[.*?\]","\"integer yresolution\" ["+str(height)+"]",t)
    if res:
        fd, fp = mkstemp(prefix=project.Name,suffix=os.path.splitext(project.Template)[-1])
        os.close(fd)
        f = open(fp,"w")
        f.write(t)
        f.close()
        project.PageResult = fp
        os.remove(fp)
        App.ActiveDocument.recompute()

    p = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Render")
    if external:
        rpath = p.GetString("LuxRenderPath","")
        args = p.GetString("LuxParameters","")
    else:
        rpath = p.GetString("LuxConsolePath","")
        args = p.GetString("LuxParameters","")
    if not rpath:
        App.Console.PrintError("Unable to locate renderer executable. Please set the correct path in Edit -> Preferences -> Render")
        return
    if args:
        args += " "

    # Call Luxrender
    cmd = prefix + rpath + " " + args + project.PageResult + "\n"
    App.Console.PrintMessage(cmd)
    try:
        p = Popen(shlex.split(cmd))
    except OSError as e:
        App.Console.PrintError("Luxrender call failed: '" + e.strerror +"'\n")

    return

