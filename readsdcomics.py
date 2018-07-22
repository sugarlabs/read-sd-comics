#! /usr/bin/env python

# Copyright (C) 2010 James D. Simmons <nicestep@gmail.com>
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
import os
import logging
import time
import zipfile
from zipfile import BadZipfile
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
import pygame
import re
from gi.repository import Pango
from sugar3 import mime
from sugar3.activity import activity
from sugar3.graphics.alert import NotifyAlert
from sugar3.graphics import style

_NEW_TOOLBAR_SUPPORT = True
try:
    from sugar3.graphics.toolbarbox import ToolbarBox
    from sugar3.graphics.toolbarbox import ToolbarButton
    from sugar3.activity.widgets import StopButton
    from readtoolbar import ViewToolbar
    from sugar3.graphics.toolbutton import ToolButton
    from sugar3.graphics.menuitem import MenuItem
    from mybutton import MyActivityToolbarButton
except:
    _NEW_TOOLBAR_SUPPORT = False
    from readtoolbar import ReadToolbar, ViewToolbar

from gettext import gettext as _
from gi.repository import GObject
from decimal import *

_TOOLBAR_READ = 1

_logger = logging.getLogger('read-sd-comics')

class ReadSDComics(activity.Activity):
    __gsignals__ = {
        'go-fullscreen': (GObject.SignalFlags.RUN_FIRST,
                          None,
                          ([]))
    }

    def __init__(self, handle):
        "The entry point to the Activity"
        activity.Activity.__init__(self, handle)

        self._object_id = handle.object_id
        self.zoom_image_to_fit = True
        self.total_pages = 0

        self.connect("draw", self.__draw_cb)
        self.connect("delete_event", self.delete_cb)
       
        if _NEW_TOOLBAR_SUPPORT:
            self.create_new_toolbar()
        else:
            self.create_old_toolbar()

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.props.shadow_type = Gtk.ShadowType.NONE
        self.image = Gtk.Image()
        self.eventbox = Gtk.EventBox()
        self.eventbox.add(self.image)
        self.image.show()
        self.eventbox.show()
        self.scrolled.add_with_viewport(self.eventbox)
        self.eventbox.set_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.eventbox.set_can_focus(True)
        self.eventbox.connect("key_press_event", self.keypress_cb)
        self.eventbox.connect("button_press_event", self.buttonpress_cb)
        
        self._filechooser = Gtk.FileChooserWidget(
            action=Gtk.FileChooserAction.OPEN)
        filter = Gtk.FileFilter()
        filter.add_mime_type('application/zip')
        filter.add_mime_type('application/x-cbz')
        self._filechooser.set_filter(filter)
        self._filechooser.set_current_folder("/media")
        self.copy_button = Gtk.Button(_("Read Comic"))
        self.copy_button.connect('clicked',  self.select_comic_path)
        self.copy_button.show()
        self._filechooser.set_extra_widget(self.copy_button)
        preview = Gtk.Image()
        self._filechooser.set_preview_widget(preview)
        self._filechooser.connect("update-preview", 
                                  self.update_preview_cb, preview)

        vbox = Gtk.VBox()
        vbox.pack_start(self.scrolled, True, True, 0)
        vbox.pack_end(self._filechooser, True, True, 0)
        self.set_canvas(vbox)
        if self._object_id is None:
            self.scrolled.hide()
            self._filechooser.show()
        else:
            self.scrolled.show()
            self._filechooser.hide()
           
        vbox.show()

        self.page = 0
        self.saved_screen_width = 0
        self.eventbox.grab_focus()
        
        # pixmap = Gdk.Pixmap(None, 1, 1, 1)
        # color = Gdk.Color()
        # self.hidden_cursor = Gdk.Cursor.new(pixmap, pixmap, color, color, 0, 0)
        self.cursor_visible = True

        self.link = None
        self._close_requested = False
        
    def select_comic_path(self,  widget,  data=None):
        filename = self._filechooser.get_filename()
        self._filechooser.hide()
        self.scrolled.show()
        self.link = filename
        self.metadata['title'] = self.make_new_filename(self.link)
        self._load_document(filename)   

    def create_old_toolbar(self):
        toolbox = activity.ActivityToolbox(self)
        activity_toolbar = toolbox.get_activity_toolbar()
        activity_toolbar.keep.props.visible = False
        activity_toolbar.share.props.visible = False
        
        self.read_toolbar = ReadToolbar()
        toolbox.add_toolbar(_('Read'), self.read_toolbar)
        self.read_toolbar.show()
        self.read_toolbar.set_activity(self)

        self.view_toolbar = ViewToolbar()
        toolbox.add_toolbar(_('View'), self.view_toolbar)
        self.view_toolbar.set_activity(self)
        self.view_toolbar.connect('go-fullscreen',
                self.__view_toolbar_go_fullscreen_cb)
        self.view_toolbar.show()

        self.set_toolbox(toolbox)
        toolbox.show()

        # start on the read toolbar
        self.toolbox.set_current_toolbar(_TOOLBAR_READ)

    def update_preview_cb(self, file_chooser, preview):
        filename = file_chooser.get_preview_filename()
        try:
            file_mimetype = mime.get_for_file(filename)
            if file_mimetype  == 'application/x-cbz' or file_mimetype == 'application/zip':
                fname = self.extract_image(filename)
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(fname, 
                    style.zoom(320), style.zoom(240))
                preview.set_from_pixbuf(pixbuf)
                have_preview = True
                os.remove(fname)
            else:
                have_preview = False
        except:
            have_preview = False
        file_chooser.set_preview_widget_active(have_preview)
        return

    def extract_image(self,  filename):
        zf = zipfile.ZipFile(filename, 'r')
        image_files = zf.namelist()
        image_files.sort()
        file_to_extract = image_files[0]
        extract_new_filename = self.make_new_filename(file_to_extract)
        if extract_new_filename is None or extract_new_filename == '':
            # skip over directory name if the images are in a subdirectory.
            file_to_extract = image_files[1]
            extract_new_filename = self.make_new_filename(file_to_extract)
            
        if len(image_files) > 0:
            if self.save_extracted_file(zf, file_to_extract):
                fname = os.path.join(self.get_activity_root(), 'instance',  
                                     extract_new_filename)
                return fname

    def create_new_toolbar(self):
        toolbar_box = ToolbarBox()

        activity_button = MyActivityToolbarButton(self)
        toolbar_box.toolbar.insert(activity_button, 0)
        activity_button.show()

        self.connect('go-fullscreen', \
            self.__view_toolbar_go_fullscreen_cb)

        self.back = ToolButton('go-previous')
        self.back.set_tooltip(_('Back'))
        self.back.props.sensitive = False
        palette = self.back.get_palette()
        self.menu_prev_page = MenuItem(text_label= _("Previous page"))
        palette.menu.append(self.menu_prev_page) 
        self.menu_prev_page.show_all()        
        self.back.connect('clicked', self.go_back_cb)
        self.menu_prev_page.connect('activate', self.go_back_cb)
        toolbar_box.toolbar.insert(self.back, -1)
        self.back.show()

        self.forward = ToolButton('go-next')
        self.forward.set_tooltip(_('Forward'))
        self.forward.props.sensitive = False
        palette = self.forward.get_palette()
        self.menu_next_page = MenuItem(text_label= _("Next page"))
        palette.menu.append(self.menu_next_page) 
        self.menu_next_page.show_all()        
        self.forward.connect('clicked', self.go_forward_cb)
        self.menu_next_page.connect('activate', self.go_forward_cb)
        toolbar_box.toolbar.insert(self.forward, -1)
        self.forward.show()

        num_page_item = Gtk.ToolItem()
        self.num_page_entry = Gtk.Entry()
        self.num_page_entry.set_text('0')
        self.num_page_entry.set_alignment(1)
        self.num_page_entry.connect('insert-text',
                               self.__new_num_page_entry_insert_text_cb)
        self.num_page_entry.connect('activate',
                               self.__new_num_page_entry_activate_cb)
        self.num_page_entry.set_width_chars(4)
        num_page_item.add(self.num_page_entry)
        self.num_page_entry.show()
        toolbar_box.toolbar.insert(num_page_item, -1)
        num_page_item.show()

        total_page_item = Gtk.ToolItem()
        self.total_page_label = Gtk.Label()

        label_attributes = Pango.AttrList()
        # label_attributes.insert(Pango.AttrSize(14000, 0, -1))
        # label_attributes.insert(Pango.AttrForeground(65535, 65535, 
                                                     # 65535, 0, -1))
        self.total_page_label.set_attributes(label_attributes)

        self.total_page_label.set_text(' / 0')
        total_page_item.add(self.total_page_label)
        self.total_page_label.show()
        toolbar_box.toolbar.insert(total_page_item, -1)
        total_page_item.show()

        spacer = Gtk.SeparatorToolItem()
        toolbar_box.toolbar.insert(spacer, -1)
        spacer.show()
  
        self._zoom_out = ToolButton('zoom-out')
        self._zoom_out.set_tooltip(_('Zoom out'))
        self._zoom_out.connect('clicked', self._zoom_out_cb)
        toolbar_box.toolbar.insert(self._zoom_out, -1)
        self._zoom_out.props.sensitive = False
        self._zoom_out.show()

        self._zoom_in = ToolButton('zoom-in')
        self._zoom_in.set_tooltip(_('Zoom in'))
        self._zoom_in.connect('clicked', self._zoom_in_cb)
        toolbar_box.toolbar.insert(self._zoom_in, -1)
        self._zoom_in.props.sensitive = True
        self._zoom_in.show()

        self._fullscreen = ToolButton('view-fullscreen')
        self._fullscreen.set_tooltip(_('Fullscreen'))
        self._fullscreen.connect('clicked', self._fullscreen_cb)
        toolbar_box.toolbar.insert(self._fullscreen, -1)
        self._fullscreen.show()
        
        separator = Gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar_box.toolbar.insert(separator, -1)
        separator.show()

        stop_button = StopButton(self)
        stop_button.props.accelerator = '<Ctrl><Shift>Q'
        toolbar_box.toolbar.insert(stop_button, -1)
        stop_button.show()

        self.set_toolbar_box(toolbar_box)
        toolbar_box.show()

    def _zoom_in_cb(self, button):
        self._zoom_in.props.sensitive = False
        self._zoom_out.props.sensitive = True
        self.zoom_to_width()
    
    def _zoom_out_cb(self, button):
        self._zoom_in.props.sensitive = True
        self._zoom_out.props.sensitive = False
        self.zoom_to_fit()

    def enable_zoom_in(self):
        self._zoom_in.props.sensitive = True
        self._zoom_out.props.sensitive = False

    def enable_zoom_out(self):
        self._zoom_in.props.sensitive = False
        self._zoom_out.props.sensitive = True

    def _fullscreen_cb(self, button):
        self.emit('go-fullscreen')

    def __new_num_page_entry_insert_text_cb(self, entry, text, length, position):
        if not re.match('[0-9]', text):
            entry.emit_stop_by_name('insert-text')
            return True
        return False

    def __new_num_page_entry_activate_cb(self, entry):
        if entry.props.text:
            page = int(entry.props.text) - 1
        else:
            page = 0

        if page >= self.total_pages:
            page = self.total_pages - 1
        elif page < 0:
            page = 0

        self.set_current_page(page)
        self.show_page(page)
        entry.props.text = str(page + 1)
        self.update_nav_buttons()

    def go_back_cb(self, button):
        self.previous_page()
    
    def go_forward_cb(self, button):
        self.next_page()
    
    def update_nav_buttons(self):
        current_page = self.page
        self.back.props.sensitive = current_page > 0
        self.forward.props.sensitive = \
            current_page < self.total_pages - 1
        
        self.num_page_entry.props.text = str(current_page + 1)
        self.total_page_label.props.label = \
            ' / ' + str(self.total_pages)

    def set_total_pages(self, pages):
        self.total_pages = pages

    def setToggleButtonState(self,button,b,id):
        button.handler_block(id)
        button.set_active(b)
        button.handler_unblock(id)

    def buttonpress_cb(self, widget, event):
        widget.grab_focus()

    def __view_toolbar_go_fullscreen_cb(self, view_toolbar):
        self.fullscreen()

    def zoom_to_width(self):
        self.zoom_image_to_fit = False
        self.show_page(self.page)

    def zoom_to_fit(self):
        self.zoom_image_to_fit = True
        self.show_page(self.page)

    def keypress_cb(self, widget, event):
        "Respond when the user presses Escape or one of the arrow keys"
        keyname = Gdk.keyval_name(event.keyval)
        if keyname == 'Page_Up':
            self.previous_page()
            return True
        if keyname == 'Page_Down' :
            self.next_page()
            return True
        if keyname == 'KP_Right':
            self.scroll_down()
            return True
        if keyname == 'Down' or keyname == 'KP_Down':
            self.scroll_down()
            return True
        if keyname == 'Up' or keyname == 'KP_Up':
            self.scroll_up()
            return True
        if keyname == 'KP_Left':
            self.scroll_up()
            return True
        if keyname == 'KP_Home':
            if self.cursor_visible:
                self.window.set_cursor(self.hidden_cursor)
                self.cursor_visible = False
            else:
                self.window.set_cursor(None)
                self.cursor_visible = True
            return True
        if keyname == 'plus':
            self.view_toolbar.enable_zoom_out()
            self.zoom_to_width()
            return True
        if keyname == 'minus':
            self.view_toolbar.enable_zoom_in()
            self.zoom_to_fit()
            return True
        return False

    def scroll_down(self):
        v_adjustment = self.scrolled.get_vadjustment()
        if v_adjustment.value == v_adjustment.upper - v_adjustment.page_size:
            self.next_page()
            return
        if v_adjustment.value < v_adjustment.upper - v_adjustment.page_size:
            new_value = v_adjustment.value + v_adjustment.step_increment
            if new_value > v_adjustment.upper - v_adjustment.page_size:
                new_value = v_adjustment.upper - v_adjustment.page_size
            v_adjustment.value = new_value

    def scroll_up(self):
        v_adjustment = self.scrolled.get_vadjustment()
        if v_adjustment.value == v_adjustment.lower:
            self.previous_page()
            return
        if v_adjustment.value > v_adjustment.lower:
            new_value = v_adjustment.value - v_adjustment.step_increment
            if new_value < v_adjustment.lower:
                new_value = v_adjustment.lower
            v_adjustment.value = new_value

    def previous_page(self):
        page = self.page
        page=page-1
        if page < 0: page=0
        if self.save_extracted_file(self.zf, self.image_files[page]) == True:
            fname = os.path.join(self.get_activity_root(), 'instance',  self.make_new_filename(self.image_files[page]))
            self.show_image(fname)
            os.remove(fname)
        v_adjustment = self.scrolled.get_vadjustment()
        v_adjustment.value = v_adjustment.upper - v_adjustment.page_size
        if _NEW_TOOLBAR_SUPPORT:
            self.set_current_page(page)
        else:
            self.read_toolbar.set_current_page(page)
        self.page = page

    def set_current_page(self, page):
        self.page = page
        if _NEW_TOOLBAR_SUPPORT:
            self.update_nav_buttons()

    def next_page(self):
        page = self.page
        page = page + 1
        if page >= len(self.image_files): page=len(self.image_files) - 1
        if self.save_extracted_file(self.zf, self.image_files[page]) == True:
            fname = os.path.join(self.get_activity_root(), 'instance',  self.make_new_filename(self.image_files[page]))
            self.show_image(fname)
            os.remove(fname)
        v_adjustment = self.scrolled.get_vadjustment()
        v_adjustment.value = v_adjustment.lower
        if _NEW_TOOLBAR_SUPPORT:
            self.set_current_page(page)
        else:
            self.read_toolbar.set_current_page(page)
        self.page = page

    def __draw_cb(self, widget, cr):
        screen_width = Gdk.Screen.width()
        screen_height = Gdk.Screen.height()
        if self.saved_screen_width != screen_width and self.saved_screen_width != 0:
            self.show_page(self.page)
        self.saved_screen_width = screen_width
        return False

    def show_page(self, page):
        if self.save_extracted_file(self.zf, self.image_files[page]) == True:
            fname = os.path.join(self.get_activity_root(), 'instance',  self.make_new_filename(self.image_files[page]))
            self.show_image(fname)
            os.remove(fname)
        
    def show_image(self, filename):
        "display a resized image in a full screen window"
        TOOLBOX_HEIGHT = 60
        BORDER_WIDTH =  30
        # get the size of the fullscreen display
        screen_width = Gdk.Screen.width()
        screen_width = screen_width - BORDER_WIDTH
        screen_height = Gdk.Screen.height()
        screen_height = screen_height - TOOLBOX_HEIGHT
        # get the size of the image.
        im = pygame.image.load(filename)
        image_width, image_height = im.get_size()
        getcontext().prec = 7
        s_a_ratio = Decimal(screen_height) / Decimal(screen_width)
        i_a_ratio = Decimal(image_height) / Decimal(image_width)
        new_width = image_width
        new_height = image_height
        if self.zoom_image_to_fit == True:
            if s_a_ratio >= i_a_ratio:
                new_width = screen_width
                new_height = image_height * screen_width
                if image_width > 1:
                    new_height /= image_width

                if new_height > screen_width:
                    new_height *= screen_width
                    if new_width > 1:
                        new_height /= new_width
                    new_width = screen_width
            else:
                new_height = screen_height
                new_width = image_width * screen_height
                if image_height > 1:
                    new_width /= image_height
                if new_width > screen_height:
                    new_width *= screen_height
                    if new_height > 1:
                        new_width /= new_height
                    new_height = screen_height
        else:
            new_width = screen_width
            new_height = image_height * screen_width
            if image_width > 1:
                new_height /= image_width

            if new_height > screen_width:
                new_height *= screen_width
                if new_width > 1:
                    new_height /= new_width
                new_width = screen_width
        
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
        scaled_buf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)
        self.image.set_from_pixbuf(scaled_buf)
        self.image.show()
 
    def save_extracted_file(self, zipfile, filename):
        "Extract the file to a temp directory for viewing"
        try:
            filebytes = zipfile.read(filename)
        except BadZipfile, err:
            print 'Error opening the zip file: %s' % (err)
            return False
        except KeyError,  err:
            self._alert('Key Error', 'Zipfile key not found: '  + str(filename))
            return
        outfn = self.make_new_filename(filename)
        if (outfn == ''):
            return False
        fname = os.path.join(self.get_activity_root(), 'instance',  outfn)
        f = open(fname, 'w')
        try:
            f.write(filebytes)
        finally:
            f.close
        return True

    def read_file(self, file_path):
        """Load a file from the datastore on activity start"""
        link_file = open(file_path,"r")
        self.link = link_file.readline()
        link_file.close()
        self.get_saved_page_number()
        self._load_document(self.link)

    def delete_cb(self, widget, event):
        return False

    def make_new_filename(self, filename):
        partition_tuple = filename.rpartition('/')
        return partition_tuple[2]
    
    def get_saved_page_number(self):
        title = self.metadata.get('title', '')
        if not title[len(title)- 1].isdigit():
            self.page = 0
        else:
            i = len(title) - 1
            page = ''
            while (title[i].isdigit() and i > 0):
                page = title[i] + page
                i = i - 1
            if title[i] == 'P':
                self.page = int(page) - 1
            else:
                # not a page number; maybe a volume number.
                self.page = 0
        
    def save_page_number(self):
        title = self.metadata.get('title', '')
        self.metadata['title_set_by_user'] = '1'
        if not title[len(title)- 1].isdigit():
            title = title + ' P' +  str(self.page + 1)
        else:
            i = len(title) - 1
            while (title[i].isdigit() and i > 0):
                i = i - 1
            if title[i] == 'P':
                title = title[0:i] + 'P' + str(self.page + 1)
            else:
                title = title + ' P' + str(self.page + 1)
        self.metadata['title'] = title

    def _load_document(self, file_path):
        "Read the Zip file containing the images"
        if not os.path.exists(file_path):
            self._alert('Error', 'File ' + file_path + ' does not exist.')
            return
        
        if zipfile.is_zipfile(file_path):
            self.zf = zipfile.ZipFile(file_path, 'r')
            self.image_files = self.zf.namelist()
            self.image_files.sort()
            i = 0
            valid_endings = ('.jpg',  '.jpeg', '.JPEG',  '.JPG', '.gif', '.GIF', '.tiff', '.TIFF', '.png', '.PNG')
            while i < len(self.image_files):
                newfn = self.make_new_filename(self.image_files[i])
                if newfn.endswith(valid_endings):
                    i = i + 1
                else:   
                    del self.image_files[i]
            self.show_page(self.page)
            if _NEW_TOOLBAR_SUPPORT:
                self.set_total_pages(len(self.image_files))
                self.set_current_page(self.page)
            else:
                self.read_toolbar.set_total_pages(len(self.image_files))
                self.read_toolbar.set_current_page(self.page)
        else:
            self._alert('Error', 'Not a zipfile ' + file_path)

    def write_file(self, file_path):
        "Save meta data for the file."
        
        self.save_page_number()
        self.metadata['activity'] = self.get_bundle_id()
        out = open(file_path, 'w')
        if self.link is None:
            self.link = 'No File'
        out.write(self.link)
        out.close()

    def can_close(self):
        self._close_requested = True
        return True

    def _alert(self, title, text=None):
        alert = NotifyAlert(timeout=15)
        alert.props.title = title
        alert.props.msg = text
        self.add_alert(alert)
        alert.connect('response', self._alert_cancel_cb)
        alert.show()

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)
