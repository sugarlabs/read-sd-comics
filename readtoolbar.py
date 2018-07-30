# Copyright (C) 2010, James Simmons <nicestep@gmail.com>
# Adapted from code Copyright (C) Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify
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
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import logging
from gettext import gettext as _
import re

from gi.repository import Pango
from gi.repository import GObject
from gi.repository import Gtk

from sugar3.graphics.toolbutton import ToolButton
from sugar3.graphics.menuitem import MenuItem
from sugar3.graphics.toggletoolbutton import ToggleToolButton
from sugar3.activity import activity

class ReadToolbar(Gtk.Toolbar):
    __gtype_name__ = 'ReadToolbar'

    def __init__(self):
        GObject.GObject.__init__(self)
        self.back = ToolButton('go-previous')
        self.back.set_tooltip(_('Back'))
        self.back.props.sensitive = False
        palette = self.back.get_palette()
        self.prev_page = MenuItem(text_label= _("Previous page"))
        palette.menu.append(self.prev_page) 
        self.prev_page.show_all()        
        self.back.connect('clicked', self.go_back_cb)
        self.prev_page.connect('activate', self.go_back_cb)
        self.insert(self.back, -1)
        self.back.show()

        self.forward = ToolButton('go-next')
        self.forward.set_tooltip(_('Forward'))
        self.forward.props.sensitive = False
        palette = self.forward.get_palette()
        self.next_page = MenuItem(text_label= _("Next page"))
        palette.menu.append(self.next_page) 
        self.next_page.show_all()        
        self.forward.connect('clicked', self.go_forward_cb)
        self.next_page.connect('activate', self.go_forward_cb)
        self.insert(self.forward, -1)
        self.forward.show()

        num_page_item = Gtk.ToolItem()

        self._num_page_entry = Gtk.Entry()
        self._num_page_entry.set_text('0')
        self._num_page_entry.set_alignment(1)
        self._num_page_entry.connect('insert-text',
                                     self._num_page_entry_insert_text_cb)
        self._num_page_entry.connect('activate',
                                     self._num_page_entry_activate_cb)

        self._num_page_entry.set_width_chars(4)

        num_page_item.add(self._num_page_entry)
        self._num_page_entry.show()

        self.insert(num_page_item, -1)
        num_page_item.show()

        total_page_item = Gtk.ToolItem()

        self._total_page_label = Gtk.Label()

        self._total_page_label.set_text(' / 0')
        total_page_item.add(self._total_page_label)
        self._total_page_label.show()

        self.insert(total_page_item, -1)
        total_page_item.show()

    def _num_page_entry_insert_text_cb(self, entry, text, length, position):
        if not re.match('[0-9]', text):
            entry.emit_stop_by_name('insert-text')
            return True
        return False

    def _num_page_entry_activate_cb(self, entry):
        if entry.props.text:
            page = int(entry.props.text) - 1
        else:
            page = 0

        if page >= self.total_pages:
            page = self.total_pages - 1
        elif page < 0:
            page = 0

        self.current_page = page
        self.activity.set_current_page(page)
        self.activity.show_page(page)
        entry.props.text = str(page + 1)
        self._update_nav_buttons()
        
    def go_back_cb(self, button):
        self.activity.previous_page()
    
    def go_forward_cb(self, button):
        self.activity.next_page()
    
    def _update_nav_buttons(self):
        current_page = self.current_page
        self.back.props.sensitive = current_page > 0
        self.forward.props.sensitive = \
            current_page < self.total_pages - 1
        
        self._num_page_entry.props.text = str(current_page + 1)
        self._total_page_label.props.label = \
            ' / ' + str(self.total_pages)

    def set_total_pages(self, pages):
        self.total_pages = pages
        
    def set_current_page(self, page):
        self.current_page = page
        self._update_nav_buttons()
        
    def set_activity(self, activity):
        self.activity = activity

    def setToggleButtonState(self,button,b,id):
        button.handler_block(id)
        button.set_active(b)
        button.handler_unblock(id)

class ViewToolbar(Gtk.Toolbar):
    __gsignals__ = {
        'go-fullscreen': (GObject.SignalFlags.RUN_FIRST,
                          None,
                          ([]))
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self._zoom_out = ToolButton('zoom-out')
        self._zoom_out.set_tooltip(_('Zoom out'))
        self._zoom_out.connect('clicked', self._zoom_out_cb)
        self.insert(self._zoom_out, -1)
        self._zoom_out.props.sensitive = False
        self._zoom_out.show()

        self._zoom_in = ToolButton('zoom-in')
        self._zoom_in.set_tooltip(_('Zoom in'))
        self._zoom_in.connect('clicked', self._zoom_in_cb)
        self.insert(self._zoom_in, -1)
        self._zoom_in.props.sensitive = True
        self._zoom_in.show()

        spacer = Gtk.SeparatorToolItem()
        spacer.props.draw = False
        self.insert(spacer, -1)
        spacer.show()

        self._fullscreen = ToolButton('view-fullscreen')
        self._fullscreen.set_tooltip(_('Fullscreen'))
        self._fullscreen.connect('clicked', self._fullscreen_cb)
        self.insert(self._fullscreen, -1)
        self._fullscreen.show()

    def _zoom_in_cb(self, button):
        self._zoom_in.props.sensitive = False
        self._zoom_out.props.sensitive = True
        self.activity.zoom_to_width()
    
    def _zoom_out_cb(self, button):
        self._zoom_in.props.sensitive = True
        self._zoom_out.props.sensitive = False
        self.activity.zoom_to_fit()

    def enable_zoom_in(self):
        self._zoom_in.props.sensitive = True
        self._zoom_out.props.sensitive = False

    def enable_zoom_out(self):
        self._zoom_in.props.sensitive = False
        self._zoom_out.props.sensitive = True

    def set_activity(self, activity):
        self.activity = activity

    def _fullscreen_cb(self, button):
        self.emit('go-fullscreen')
