"""

    KeepNote
    Graphical User Interface for KeepNote Application

"""

#
#  KeepNote
#  Copyright (c) 2008-2009 Matt Rasmussen
#  Author: Matt Rasmussen <rasmus@mit.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
#


# python imports
import gettext
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

_ = gettext.gettext


# pygtk imports
import pygtk
pygtk.require('2.0')
from gtk import gdk
import gtk.glade
import gobject
import pango

# keepnote imports
import keepnote
from keepnote import \
    KeepNoteError, \
    ensure_unicode, \
    unicode_gtk, \
    FS_ENCODING
from keepnote.notebook import \
     NoteBookError, \
     NoteBookVersionError
from keepnote import notebook as notebooklib
from keepnote import tasklib
from keepnote.gui import \
     get_resource, \
     get_resource_image, \
     get_resource_pixbuf, \
     get_accel_file, \
     Action, \
     ToggleAction, \
     add_actions, \
     CONTEXT_MENU_ACCEL_PATH, \
     FileChooserDialog

from keepnote.gui.icons import \
     lookup_icon_filename
import keepnote.search
from keepnote.gui import richtext
from keepnote.gui import \
    dialog_app_options, \
    dialog_drag_drop_test, \
    dialog_wait, \
    dialog_update_notebook, \
    dialog_node_icon, \
    update_file_preview
from keepnote.gui.icon_menu import IconMenu
from keepnote.gui.three_pane_viewer import ThreePaneViewer





def set_menu_icon(uimanager, path, filename):
    item = uimanager.get_widget(path)
    img = gtk.Image()
    img.set_from_pixbuf(get_resource_pixbuf(filename))
    item.set_image(img) 



class KeepNoteWindow (gtk.Window):
    """Main windows for KeepNote"""

    def __init__(self, app):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        
        self.app = app # application object

        # window state
        self._maximized = False   # True if window is maximized
        self._iconified = False   # True if window is minimized
        self._tray_icon = None

        self.uimanager = gtk.UIManager()
        self.accel_group = self.uimanager.get_accel_group()
        self.add_accel_group(self.accel_group)

        self.init_key_shortcuts()
        self.init_layout()
        self.setup_systray()

        # load preferences for the first time
        self.load_preferences(True)
        

    def init_layout(self):
        # init main window
        self.set_title(keepnote.PROGRAM_NAME)
        self.set_default_size(*keepnote.DEFAULT_WINDOW_SIZE)
        self.set_icon_list(get_resource_pixbuf("keepnote-16x16.png"),
                           get_resource_pixbuf("keepnote-32x32.png"),
                           get_resource_pixbuf("keepnote-64x64.png"))


        # main window signals
        self.connect("delete-event", lambda w,e: self._on_close())
        self.connect("window-state-event", self._on_window_state)
        self.connect("size-allocate", self._on_window_size)
        self.app.pref.changed.add(self._on_app_options_changed)
        

        # viewer
        self.viewer = self.new_viewer()


        #====================================
        # Dialogs
        
        self.app_options_dialog = dialog_app_options.ApplicationOptionsDialog(self)
        self.drag_test = dialog_drag_drop_test.DragDropTestDialog(self)
        self.node_icon_dialog = dialog_node_icon.NodeIconDialog(self)
        
        
        #====================================
        # Layout
        
        # vertical box
        main_vbox = gtk.VBox(False, 0)
        self.add(main_vbox)
        
        # menu bar
        main_vbox.set_border_width(0)
        self.menubar = self.make_menubar()
        main_vbox.pack_start(self.menubar, False, True, 0)
        
        # toolbar
        main_vbox.pack_start(self.make_toolbar(), False, True, 0)          
        
        main_vbox2 = gtk.VBox(False, 0)
        main_vbox2.set_border_width(1)
        main_vbox.pack_start(main_vbox2, True, True, 0)

        # viewer
        main_vbox2.pack_start(self.viewer, True, True, 0)


        # status bar
        status_hbox = gtk.HBox(False, 0)
        main_vbox.pack_start(status_hbox, False, True, 0)
        
        # message bar
        self.status_bar = gtk.Statusbar()      
        status_hbox.pack_start(self.status_bar, False, True, 0)
        self.status_bar.set_property("has-resize-grip", False)
        self.status_bar.set_size_request(300, -1)
        
        # stats bar
        self.stats_bar = gtk.Statusbar()
        status_hbox.pack_start(self.stats_bar, True, True, 0)

        # add viewer menus
        add_actions(self.actiongroup, self.viewer.get_actions())
        for s in self.viewer.get_ui():
            ui_id = self.uimanager.add_ui_from_string(s)
        self.viewer.setup_menus(self.uimanager)

        

    def get_accel_group(self):
        """Returns the accel group for the window"""
        return self.accel_group()


    def init_key_shortcuts(self):
        """Setup key shortcuts for the window"""
        
        accel_file = get_accel_file()
        if os.path.exists(accel_file):
            gtk.accel_map_load(accel_file)
        else:
            gtk.accel_map_save(accel_file)


    def setup_systray(self):
        """Setup systray for window"""

        # system tray icon
        if gtk.gtk_version > (2, 10):
            if not self._tray_icon:
                self._tray_icon = gtk.StatusIcon()
                self._tray_icon.set_from_pixbuf(get_resource_pixbuf("keepnote-32x32.png"))
                self._tray_icon.set_tooltip(keepnote.PROGRAM_NAME)
                self._tray_icon.connect("activate", self._on_tray_icon_activate)

            self._tray_icon.set_property("visible", self.app.pref.use_systray)
            
        else:
            self._tray_icon = None


    def new_viewer(self):

        viewer = ThreePaneViewer(self.app, self)
        viewer.connect("error", lambda w,m,e: self.error(m, e))
        viewer.connect("status", lambda w,m,b: self.set_status(m, b))
        viewer.connect("window-request", self._on_window_request)
        viewer.connect("history-changed", self._on_history_changed)

        # context menus
        self.make_context_menus(viewer)

        return viewer


    #===============================================
    # accessors

    def get_app(self):
        """Return application object"""
        return self.app


    def get_viewer(self):
        """Return window's viewer"""
        return self.viewer
    

    def get_notebook(self):
        """Return the currently loaded notebook"""
        return self.viewer.get_notebook()

    
    def get_current_page(self):
        """Return the currently selected page"""
        return self.viewer.get_current_page()
        
        
                

    #=================================================
    # Window manipulation

    def minimize_window(self):
        """Minimize the window (block until window is minimized"""
        
        if self._iconified:
            return

        # TODO: add timer in case minimize fails
        def on_window_state(window, event):            
            if event.new_window_state & gtk.gdk.WINDOW_STATE_ICONIFIED:
                gtk.main_quit()
        sig = self.connect("window-state-event", on_window_state)
        self.iconify()
        gtk.main()
        self.disconnect(sig)


    def restore_window(self):
        """Restore the window from minimization"""
        self.deiconify()
        self.present()


    #=========================================================
    # main window gui callbacks

    def _on_window_state(self, window, event):
        """Callback for window state"""

        # keep track of maximized and minimized state
        self._iconified = bool(event.new_window_state & 
                               gtk.gdk.WINDOW_STATE_ICONIFIED)

        # TODO: add call to maximize window to help MS windows

        self._maximized = bool(event.new_window_state & 
                               gtk.gdk.WINDOW_STATE_MAXIMIZED)


    def _on_window_size(self, window, event):
        """Callback for resize events"""

        # record window size if it is not maximized or minimized
        if not self._maximized and not self._iconified:
            self.app.pref.window_size = self.get_size()


    def _on_app_options_changed(self):
        self.load_preferences()


    def _on_tray_icon_activate(self, icon):
        """Try icon has been clicked in system tray"""
        
        if self.is_active():
            self.minimize_window()
        else:
            self.restore_window()

    
    #==============================================
    # Application preferences     
    
    def load_preferences(self, first_open=False):
        """Load preferences"""
        
        if first_open:
            self.resize(*self.app.pref.window_size)
            if self.app.pref.window_maximized:
                self.maximize()

        self.enable_spell_check(self.app.pref.spell_check)
        self.setup_systray()

        if self.app.pref.use_systray:
            self.set_property("skip-taskbar-hint", self.app.pref.skip_taskbar)
        
        self.set_recent_notebooks_menu(self.app.pref.recent_notebooks)

        self.viewer.load_preferences(self.app.pref, first_open)
    

    def save_preferences(self):
        """Save preferences"""

        self.app.pref.window_maximized = self._maximized
        self.viewer.save_preferences(self.app.pref)
        self.app.pref.last_treeview_name_path = []

        if self.app.pref.use_last_notebook and self.viewer.get_notebook():
            self.app.pref.default_notebook = self.viewer.get_notebook().get_path()
        
        self.app.pref.write()
        
        
    def set_recent_notebooks_menu(self, recent_notebooks):
        """Set the recent notebooks in the file menu"""

        menu = self.uimanager.get_widget("/main_menu_bar/File/Open Recent Notebook")

        # init menu
        if menu.get_submenu() is None:
            submenu = gtk.Menu()
            submenu.show()
            menu.set_submenu(submenu)
        menu = menu.get_submenu()

        # clear menu
        menu.foreach(lambda x: menu.remove(x))

        def make_filename(filename):
            if len(filename) > 30:
                base = os.path.basename(filename)
                pre = max(30 - len(base), 10)
                return os.path.join(filename[:pre] + u"...", base)
            else:
                return filename

        def make_func(filename):
            return lambda w: self.open_notebook(filename)

        # populate menu
        for i, notebook in enumerate(recent_notebooks):
            item = gtk.MenuItem(u"%d. %s" % (i+1, make_filename(notebook)))
            item.connect("activate", make_func(notebook))
            item.show()
            menu.append(item)

           
    #=============================================
    # Notebook open/save/close UI

    def on_new_notebook(self):
        """Launches New NoteBook dialog"""
        
        dialog = FileChooserDialog(
            _("New Notebook"), self, 
            action=gtk.FILE_CHOOSER_ACTION_SAVE, #CREATE_FOLDER,
            buttons=(_("Cancel"), gtk.RESPONSE_CANCEL,
                     _("New"), gtk.RESPONSE_OK),
            app=self.app,
            persistent_path="new_notebook_path")
        response = dialog.run()
        
        
        if response == gtk.RESPONSE_OK:
            # create new notebook
            if dialog.get_filename():
                self.new_notebook(unicode_gtk(dialog.get_filename()))

        dialog.destroy()
    
    
    def on_open_notebook(self):
        """Launches Open NoteBook dialog"""
        
        dialog = FileChooserDialog(
            _("Open Notebook"), self, 
            action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER, 
            buttons=(_("Cancel"), gtk.RESPONSE_CANCEL,
                     _("Open"), gtk.RESPONSE_OK),
            app=self.app,
            persistent_path="new_notebook_path")

        def on_folder_changed(filechooser):
            folder = unicode_gtk(filechooser.get_current_folder())
            
            if os.path.exists(os.path.join(folder, notebooklib.PREF_FILE)):
                filechooser.response(gtk.RESPONSE_OK)
                        
        dialog.connect("current-folder-changed", on_folder_changed)
        
        file_filter = gtk.FileFilter()
        file_filter.add_pattern("*.nbk")
        file_filter.set_name(_("Notebook (*.nbk)"))
        dialog.add_filter(file_filter)
        
        file_filter = gtk.FileFilter()
        file_filter.add_pattern("*")
        file_filter.set_name(_("All files (*.*)"))
        dialog.add_filter(file_filter)
        
        response = dialog.run()
        
        if response == gtk.RESPONSE_OK:
            # make sure start in parent directory
            if dialog.get_current_folder():
                self.app.pref.new_notebook_path = \
                    os.path.dirname(unicode_gtk(dialog.get_current_folder()))

            if dialog.get_filename():
                notebook_file = unicode_gtk(dialog.get_filename())
            self.open_notebook(notebook_file)

        dialog.destroy()

    
    def _on_close(self):
        """Callback for window close"""
        
        self.save_preferences()
        self.close_notebook()
        if self._tray_icon:
            self._tray_icon.set_property("visible", False)
            
        return False
    

    def close(self):
        """Close the window"""

        self.emit("delete-event", None)
        

    
    #===============================================
    # Notebook actions    

    def save_notebook(self, silent=False):
        """Saves the current notebook"""

        if self.viewer.get_notebook() is None:
            return
        
        try:
            # TODO: should this be outside exception
            self.viewer.save()
            self.viewer.get_notebook().save()

            self.set_status(_("Notebook saved"))
            
            self.set_notebook_modified(False)
            
        except Exception, e:
            if not silent:
                self.error(_("Could not save notebook"), e, sys.exc_info()[2])
                self.set_status(_("Error saving notebook"))
                return

            self.set_notebook_modified(False)

        
            
    
    def reload_notebook(self):
        """Reload the current NoteBook"""
        
        if self.viewer.get_notebook() is None:
            self.error(_("Reloading only works when a notebook is open"))
            return
        
        filename = self.viewer.get_notebook().get_path()
        self.close_notebook(False)
        self.open_notebook(filename)
        
        self.set_status(_("Notebook reloaded"))
        
        
    
    def new_notebook(self, filename):
        """Creates and opens a new NoteBook"""
        
        if self.viewer.get_notebook() is not None:
            self.close_notebook()
        
        try:
            # make sure filename is unicode
            filename = ensure_unicode(filename, FS_ENCODING)
            notebook = notebooklib.NoteBook(filename)
            notebook.create()
            notebook.close()
            self.set_status(_("Created '%s'") % notebook.get_title())
        except NoteBookError, e:
            self.error(_("Could not create new notebook"), e, sys.exc_info()[2])
            self.set_status("")
            return None
        
        return self.open_notebook(filename, new=True)
        
        
    
    def open_notebook(self, filename, new=False):
        """Opens a new notebook"""
        
        if self.viewer.get_notebook() is not None:
            self.close_notebook()
        
        # make sure filename is unicode
        filename = ensure_unicode(filename, FS_ENCODING)
        
        # TODO: should this be moved deeper?
        # convert filenames to their directories
        if os.path.isfile(filename):
            filename = os.path.dirname(filename)

        win = self

        # check version
        try:
            notebook = self.app.open_notebook(filename, self)
            notebook.node_changed.add(self.on_notebook_node_changed)

        except NoteBookVersionError, e:
            self.error(_("This version of %s cannot read this notebook.\n" 
                         "The notebook has version %d.  %s can only read %d")
                       % (keepnote.PROGRAM_NAME,
                          e.notebook_version,
                          keepnote.PROGRAM_NAME,
                          e.readable_version),
                       e, sys.exc_info()[2])
            return None

        except NoteBookError, e:            
            self.error(_("Could not load notebook '%s'") % filename,
                       e, sys.exc_info()[2])
            return None

        except Exception, e:
            # give up opening notebook
            self.error(_("Could not load notebook '%s'") % filename,
                       e, sys.exc_info()[2])
            return None



        # setup notebook
        self.set_notebook(notebook)
        
        if not new:
            self.set_status(_("Loaded '%s'") % self.viewer.get_notebook().get_title())
        
        self.set_notebook_modified(False)

        # setup auto-saving
        self.begin_auto_save()
        
        # save notebook to recent notebooks
        self.add_recent_notebook(filename)


        if self.viewer.get_notebook()._index.index_needed():
            self.update_index()

        return self.viewer.get_notebook()
        
        
    def close_notebook(self, save=True):
        """Close the NoteBook"""
        
        if self.viewer.get_notebook() is not None:
            if save:
                self.save_notebook()
            
            self.viewer.get_notebook().node_changed.remove(self.on_notebook_node_changed)
            self.viewer.get_notebook().close()
            self.set_notebook(None)
            self.set_status(_("Notebook closed"))


    def begin_auto_save(self):
        """Begin autosave callbacks"""

        if self.app.pref.autosave:
            gobject.timeout_add(self.app.pref.autosave_time, self.auto_save)
        

    def auto_save(self):
        """Callback for autosaving"""

        # NOTE: return True to activate next timeout callback
        
        if self.viewer.get_notebook() is not None:
            self.save_notebook(True)
            return self.app.pref.autosave
        else:
            return False
    

    def set_notebook(self, notebook):
        """Set the NoteBook for the window"""
        
        self.viewer.set_notebook(notebook)


    def add_recent_notebook(self, filename):
        """Add recent notebook"""
        
        if filename in self.app.pref.recent_notebooks:
            self.app.pref.recent_notebooks.remove(filename)
        
        self.app.pref.recent_notebooks = \
            [filename] + self.app.pref.recent_notebooks[:keepnote.gui.MAX_RECENT_NOTEBOOKS]

        self.app.pref.changed.notify()


    def update_index(self):
        """Update notebook index"""

        if not self.viewer.get_notebook():
            return

        def update(task):
            # do search in another thread

            # erase database first
            # NOTE: I do this right now so that corrupt databases can be
            # cleared out of the way.
            self.viewer.get_notebook()._index.clear()

            for node in self.viewer.get_notebook()._index.index_all():
                # terminate if search is canceled
                if task.aborted():
                    break
            task.finish()

        # launch task
        self.wait_dialog(_("Indexing notebook"), _("Indexing..."),
                         tasklib.Task(update))


    #=============================================================
    # viewer callbacks


    def _on_window_request(self, viewer, action):
        """Callback for requesting an action from the main window"""
        
        if action == "minimize":
            self.minimize_window()
        elif action == "restore":
            self.restore_window()
        else:
            raise Exception("unknown window request: " + str(action))
    
            
    def _on_history_changed(self, viewer, history):
        """Callback for when node browse history changes"""
        
        self.back_button.set_sensitive(history.has_back())
        self.forward_button.set_sensitive(history.has_forward())

    
    #===========================================================
    # page and folder actions

    def get_selected_nodes(self, widget="focus"):
        """
        Returns (nodes, widget) where 'nodes' are a list of selected nodes
        in widget 'widget'

        Wiget can be
           listview -- nodes selected in listview
           treeview -- nodes selected in treeview
           focus    -- nodes selected in widget with focus
        """
        
        return self.viewer.get_selected_nodes(widget)
        

    def on_new_node(self, kind, widget, pos):
        self.viewer.new_node(kind, widget, pos)
        
    
    def on_new_dir(self, widget="focus"):
        """Add new folder near selected nodes"""
        self.on_new_node(notebooklib.CONTENT_TYPE_DIR, widget, "sibling")
    
            
    
    def on_new_page(self, widget="focus"):
        """Add new page near selected nodes"""
        self.on_new_node(notebooklib.CONTENT_TYPE_PAGE, widget, "sibling")
    

    def on_new_child_page(self, widget="focus"):
        self.on_new_node(notebooklib.CONTENT_TYPE_PAGE, widget, "child")


    def on_empty_trash(self):
        """Empty Trash folder in NoteBook"""
        
        if self.viewer.get_notebook() is None:
            return

        try:
            self.viewer.get_notebook().empty_trash()
        except NoteBookError, e:
            self.error(_("Could not empty trash."), e, sys.exc_info()[2])


    def _on_history(self, offset):
        """Move forward or backward in history"""
        self.viewer.visit_history(offset)
        


    def on_search_nodes(self):
        """Search nodes"""

        # do nothing if notebook is not defined
        if not self.viewer.get_notebook():
            return

        # get words
        words = [x.lower() for x in
                 unicode_gtk(self.search_box.get_text()).strip().split()]
        
        # prepare search iterator
        nodes = keepnote.search.search_manual(self.viewer.get_notebook(), words)

        # clear listview        
        self.viewer.start_search_result()

        def search(task):
            # do search in another thread

            def gui_update(node):
                def func():
                    gtk.gdk.threads_enter()
                    self.viewer.add_search_result(node)
                    gtk.gdk.threads_leave()
                return func

            for node in nodes:
                # terminate if search is canceled
                if task.aborted():
                    break
                gobject.idle_add(gui_update(node))
                
            task.finish()

        # launch task
        self.wait_dialog(_("Searching notebook"), _("Searching..."),
                         tasklib.Task(search))


    def focus_on_search_box(self):
        """Place cursor in search box"""
        self.search_box.grab_focus()


    def on_set_icon(self, icon_file, icon_open_file, widget="focus"):
        """
        Change the icon for a node

        icon_file, icon_open_file -- icon basenames
            use "" to delete icon setting (set default)
            use None to leave icon setting unchanged
        """

        if self.viewer.get_notebook() is None:
            return

        nodes, widget = self.get_selected_nodes(widget)

        for node in nodes:

            if icon_file == u"":
                node.del_attr("icon")
            elif icon_file is not None:
                node.set_attr("icon", icon_file)

            if icon_open_file == u"":
                node.del_attr("icon_open")
            elif icon_open_file is not None:
                node.set_attr("icon_open", icon_open_file)

            node.del_attr("icon_load")
            node.del_attr("icon_open_load")



    def on_new_icon(self, widget="focus"):
        """Change the icon for a node"""

        if self.viewer.get_notebook() is None:
            return

        nodes, widget = self.get_selected_nodes(widget)

        # TODO: assume only one node is selected
        node = nodes[0]

        icon_file, icon_open_file = self.node_icon_dialog.show(node)

        print icon_file, icon_open_file

        newly_installed = set()

        # NOTE: files may be filename or basename, use isabs to distinguish
        if icon_file and os.path.isabs(icon_file) and \
           icon_open_file and os.path.isabs(icon_open_file):
            icon_file, icon_open_file = self.viewer.get_notebook().install_icons(
                icon_file, icon_open_file)
            newly_installed.add(os.path.basename(icon_file))
            newly_installed.add(os.path.basename(icon_open_file))
            
        else:
            if icon_file and os.path.isabs(icon_file):
                icon_file = self.viewer.get_notebook().install_icon(icon_file)
                newly_installed.add(os.path.basename(icon_file))

            if icon_open_file and os.path.isabs(icon_open_file):
                icon_open_file = self.viewer.get_notebook().install_icon(icon_open_file)
                newly_installed.add(os.path.basename(icon_open_file))

        # set quick picks if OK was pressed
        if icon_file is not None:
            self.viewer.get_notebook().pref.set_quick_pick_icons(
                self.node_icon_dialog.get_quick_pick_icons())

            # set notebook icons
            notebook_icons = self.viewer.get_notebook().get_icons()
            keep_set = set(self.node_icon_dialog.get_notebook_icons()) | \
                       newly_installed
            for icon in notebook_icons:
                if icon not in keep_set:
                    self.viewer.get_notebook().uninstall_icon(icon)
            
            self.viewer.get_notebook().write_preferences()

        self.on_set_icon(icon_file, icon_open_file)


    
    
    #=====================================================
    # Notebook callbacks
    
    def on_notebook_node_changed(self, nodes, recurse):
        """Callback for when the notebook changes"""
        self.set_notebook_modified(True)
        
    
    def set_notebook_modified(self, modified):
        """Set the modification state of the notebook"""
        
        if self.viewer.get_notebook() is None:
            self.set_title(keepnote.PROGRAM_NAME)
        else:
            if modified:
                self.set_title("* %s" % self.viewer.get_notebook().get_title())
                self.set_status(_("Notebook modified"))
            else:
                self.set_title("%s" % self.viewer.get_notebook().get_title())
    
    #=================================================
    # file attachments

    def on_attach_file(self, widget="focus"):

        if self.viewer.get_notebook() is None:
            return
        
        dialog = FileChooserDialog(
            _("Attach File..."), self, 
            action=gtk.FILE_CHOOSER_ACTION_OPEN,
            buttons=(_("Cancel"), gtk.RESPONSE_CANCEL,
                     _("Attach"), gtk.RESPONSE_OK),
            app=self.app,
            persistent_path="attach_file_path")
        dialog.set_default_response(gtk.RESPONSE_OK)

        # setup preview
        preview = gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.connect("update-preview", update_file_preview, preview)

        response = dialog.run()

        if response == gtk.RESPONSE_OK:
            if dialog.get_filename():
                self.attach_file(unicode_gtk(dialog.get_filename()), 
                                 widget=widget)

        dialog.destroy()


    def attach_file(self, filename, node=None, index=None, widget="focus"):
        
        if node is None:
            nodes, widget = self.get_selected_nodes(widget)
            node = nodes[0]

        # cannot attach directories (yet)
        if os.path.isdir(filename):
            return
            
        content_type = mimetypes.guess_type(filename)[0]
        if content_type is None:
            content_type = "application/octet-stream"
        
        new_filename = os.path.basename(filename)
        child = None

        try:
            path = notebooklib.get_valid_unique_filename(node.get_path(), 
                                                         new_filename)
            child = self.viewer.get_notebook().new_node(
                    content_type, 
                    path,
                    node,
                    {"payload_filename": new_filename,
                     "title": new_filename})
            child.create()
            node.add_child(child, index)
            child.set_payload(filename, new_filename)            
            child.save(True)
                
        except Exception, e:

            # remove child
            if child:
                child.delete()

            self.error(_("Error while attaching file '%s'" % filename),
                       e, sys.exc_info()[2])
                             
        

    
    #=====================================================
    # Cut/copy/paste    
    # forward cut/copy/paste to the correct widget
    
    def on_cut(self):
        """Cut callback"""
        widget = self.get_focus()
        if gobject.signal_lookup("cut-clipboard", widget) != 0:
            widget.emit("cut-clipboard")
    
    def on_copy(self):
        """Copy callback"""
        widget = self.get_focus()
        if gobject.signal_lookup("copy-clipboard", widget) != 0:
            widget.emit("copy-clipboard")

    def on_paste(self):
        """Paste callback"""
        widget = self.get_focus()
        if gobject.signal_lookup("paste-clipboard", widget) != 0:
            widget.emit("paste-clipboard")


    def on_undo(self):
        """Undo callback"""
        self.viewer.undo()

    def on_redo(self):
        """Redo callback"""
        self.viewer.redo()
    
    
    #=====================================================
    # External app viewers

    # TODO: may be move this to viewer
        
    def on_view_node_external_app(self, app, node=None, widget="focus",
                                  kind=None):
        """View a node with an external app"""

        self.save_notebook()
        
        if node is None:
            nodes, widget = self.get_selected_nodes(widget)
            if len(nodes) == 0:
                self.error(_("No notes are selected."))
                return            
            node = nodes[0]

            if kind == "page" and \
               node.get_attr("content_type") != notebooklib.CONTENT_TYPE_PAGE:
                self.error(_("Only pages can be viewed with %s.") %
                           self.app.pref.get_external_app(app).title)
                return

        try:
            if kind == "page":
                # get html file
                filename = os.path.realpath(node.get_data_file())
                
            elif kind == "file":
                # get payload file
                if not node.has_attr("payload_filename"):
                    self.error(_("Only files can be viewed with %s.") %
                               self.app.pref.get_external_app(app).title)
                    return
                filename = os.path.realpath(
                    os.path.join(node.get_path(),
                                 node.get_attr("payload_filename")))
                
            else:
                # get node dir
                filename = os.path.realpath(node.get_path())
            
            self.app.run_external_app(app, filename)
        except KeepNoteError, e:
            self.error(e.msg, e, sys.exc_info()[2])


    def view_error_log(self):        
        """View error in text editor"""

        # windows locks open files
        # therefore we should copy error log before viewing it
        try:
            filename = os.path.realpath(keepnote.get_user_error_log())
            filename2 = filename + ".bak"
            shutil.copy(filename, filename2)        

            # use text editor to view error log
            self.app.run_external_app("text_editor", filename2)
        except Exception, e:
            self.error(_("Could not open error log"), e, sys.exc_info()[2])




    #=======================================================
    # spellcheck
    
    def on_spell_check_toggle(self, widget):
        """Toggle spell checker"""
        self.enable_spell_check(widget.get_active())


    def enable_spell_check(self, enabled):
        """Spell check"""

        textview = self.viewer.editor.get_textview()
        if textview is not None:
            textview.enable_spell_check(enabled)
            
            # see if spell check became enabled
            enabled = textview.is_spell_check_enabled()

            # record state in preferences
            self.app.pref.spell_check = enabled

            # update UI to match
            self.spell_check_toggle.set_active(enabled)
    
    #==================================================
    # Help/about dialog
    
    def on_about(self):
        """Display about dialog"""

        def func(dialog, link, data):
            try:
                self.app.open_webpage(link)
            except KeepNoteError, e:
                self.error(e.msg, e, sys.exc_info()[2])
        gtk.about_dialog_set_url_hook(func, None)
        
        
        about = gtk.AboutDialog()
        about.set_name(keepnote.PROGRAM_NAME)
        about.set_version(keepnote.PROGRAM_VERSION_TEXT)
        about.set_copyright("Copyright Matt Rasmussen 2009.")
        about.set_logo(get_resource_pixbuf("keepnote-icon.png"))
        about.set_website(keepnote.WEBSITE)
        about.set_license("GPL version 2")
        about.set_translator_credits(
            "French: tb <thibaut.bethune@gmail.com>\n"
            "Turkish: Yuce Tekol <yucetekol@gmail.com>\n")

        license_file = keepnote.get_resource(u"rc", u"COPYING")
        if os.path.exists(license_file):
            about.set_license(open(license_file).read())

        #about.set_authors(["Matt Rasmussen <rasmus@mit.edu>"])
        

        about.set_transient_for(self)
        about.set_position(gtk.WIN_POS_CENTER_ON_PARENT)
        about.connect("response", lambda d,r: about.destroy())
        about.show()


    #def on_python_prompt(self):

    #    import idlelib
        #idlelib.idle
        

    #===========================================
    # Messages, warnings, errors UI/dialogs
    
    def set_status(self, text, bar="status"):
        if bar == "status":
            self.status_bar.pop(0)
            self.status_bar.push(0, text)
        elif bar == "stats":
            self.stats_bar.pop(0)
            self.stats_bar.push(0, text)
        else:
            raise Exception("unknown bar '%s'" % bar)
            
    
    def error(self, text, error=None, tracebk=None):
        """Display an error message"""
        
        dialog = gtk.MessageDialog(self.get_toplevel(), 
            flags= gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
            type=gtk.MESSAGE_ERROR, 
            buttons=gtk.BUTTONS_OK, 
            message_format=text)
        dialog.connect("response", lambda d,r: d.destroy())
        dialog.set_title(_("Error"))
        dialog.show()
        
        # add message to error log
        if error is not None:
            keepnote.log_error(error, tracebk)


    def wait_dialog(self, title, text, task):
        """Display a wait dialog"""

        dialog = dialog_wait.WaitDialog(self)
        dialog.show(title, text, task)


    def wait_dialog_test_task(self):
        # create dummy testing task
        
        def func(task):
            complete = 0.0
            while task.is_running():
                print complete
                complete = 1.0 - (1.0 - complete) * .9999
                task.set_percent(complete)
            task.finish()
        return tasklib.Task(func)
        

        
    
    #================================================
    # Menus

    def get_actions(self):

        actions = map(lambda x: Action(*x),
                      [
            ("File", None, _("_File")),

            ("New Notebook", gtk.STOCK_NEW, _("_New Notebook..."),
             "", _("Start a new notebook"),
             lambda w: self.on_new_notebook()),

            ("New Page", None, _("New _Page"),
             "<control>N", _("Create a new page"),
             lambda w: self.on_new_page()),

            ("New Child Page", None, _("New _Child Page"),
             "<control><shift>N", _("Create a new child page"),
             lambda w: self.on_new_child_page()),

            ("New Folder", None, _("New _Folder"),
             "<control><shift>M", _("Create a new folder"),
             lambda w: self.on_new_dir()),

            ("Open Notebook", gtk.STOCK_OPEN, _("_Open Notebook..."),
             "<control>O", _("Open an existing notebook"),
             lambda w: self.on_open_notebook()),
            
            ("Open Recent Notebook", gtk.STOCK_OPEN, 
             _("Open Re_cent Notebook")),

            ("Reload Notebook", gtk.STOCK_REVERT_TO_SAVED,
             _("_Reload Notebook"),
             "", _("Reload the current notebook"),
             lambda w: self.reload_notebook()),
            
            ("Save Notebook", gtk.STOCK_SAVE, _("_Save Notebook"),             
             "<control>S", _("Save the current notebook"),
             lambda w: self.save_notebook()),
            
            ("Close Notebook", gtk.STOCK_CLOSE, _("_Close Notebook"),
             "", _("Close the current notebook"),
             lambda w: self.close_notebook()),
            
            ("Export", None, _("_Export Notebook")),

            ("Import", None, _("_Import Notebook")),

            ("Quit", gtk.STOCK_QUIT, _("_Quit"),
             "<control>Q", _("Quit KeepNote"),
             lambda w: self.close()),

            #=======================================
            ("Edit", None, _("_Edit")),
            
            ("Undo", gtk.STOCK_UNDO, None,
             "<control>Z", None,
             lambda w: self.on_undo()),
            
            ("Redo", gtk.STOCK_REDO, None,
             "<control><shift>Z", None,
             lambda w: self.on_redo()),
            
            ("Cut", gtk.STOCK_CUT, None,
             "<control>X", None,
             lambda w: self.on_cut()),

            ("Copy", gtk.STOCK_COPY, None,
             "<control>C", None,
             lambda w: self.on_copy()),

            ("Paste", gtk.STOCK_PASTE, None,
             "<control>V", None,
             lambda w: self.on_paste()),

            ("Attach File", gtk.STOCK_ADD, _("_Attach File..."),
             "", _("Attach a file to the notebook"),
             lambda w: self.on_attach_file()),

            ("Empty Trash", gtk.STOCK_DELETE, _("Empty _Trash"),
             "", None,
             lambda w: self.on_empty_trash()),
            
            #========================================
            ("Search", None, _("_Search")),
            
            ("Search All Notes", gtk.STOCK_FIND, _("_Search All Notes"),
             "<control>K", None,
             lambda w: self.focus_on_search_box()),


            #========================================
            ("View", None, _("_View")),

            
            ("View Note in File Explorer", gtk.STOCK_OPEN,
             _("View Note in File Explorer"),
             "", None,
             lambda w: self.on_view_node_external_app("file_explorer")),
            
            ("View Note in Text Editor", gtk.STOCK_OPEN,
             _("View Note in Text Editor"),
             "", None,
             lambda w: self.on_view_node_external_app("text_editor",
                                                      kind="page")),

            ("View Note in Web Browser", gtk.STOCK_OPEN,
             _("View Note in Web Browser"),
             "", None,
             lambda w: self.on_view_node_external_app("web_browser",
                                                      kind="page")),

            ("Open File", gtk.STOCK_OPEN,
             _("_Open File"),
             "", None,
             lambda w: self.on_view_node_external_app("file_launcher",
                                                      kind="file")),

            #=======================================
            ("Go", None, _("_Go")),

            ("Back", gtk.STOCK_GO_BACK, _("_Back"), "", None,
             lambda w: self._on_history(-1)),

            ("Forward", gtk.STOCK_GO_FORWARD, _("_Forward"), "", None,
             lambda w: self._on_history(1)),
            
            #=========================================
            ("Options", None, _("_Options")),

            ("Update Notebook Index", None, _("_Update Notebook Index"),
             "", None,
             lambda w: self.update_index()),
            
            ("KeepNote Options", gtk.STOCK_PREFERENCES, _("KeepNote _Options"),
             "", None,
             lambda w: self.app_options_dialog.on_app_options()),

            #=========================================
            ("Help", None, _("_Help")),
            
            ("View Error Log...", gtk.STOCK_DIALOG_ERROR, _("View _Error Log..."),
             "", None,
             lambda w: self.view_error_log()),
            
            ("Drag and Drop Test...", None, _("Drag and Drop Test..."),
             "", None,
             lambda w: self.drag_test.on_drag_and_drop_test()),

            #("Python Prompt...", None, _("Python Prompt..."),
            # "", None,
            # lambda w: self.on_python_prompt()),
            
            ("About", gtk.STOCK_ABOUT, _("_About"),
             "", None,
             lambda w: self.on_about())
            ]) + \
            map(lambda x: ToggleAction(*x), [
            ("Spell Check", None, _("_Spell Check"), 
             "", None,
             self.on_spell_check_toggle)])


        # make sure recent notebooks is always visible
        recent = [x for x in actions 
                  if x.get_property("name") == "Open Recent Notebook"][0]
        recent.set_property("is-important", True)

        return actions

    def setup_menus(self, uimanager):
        u = uimanager
        set_menu_icon(u, "/main_menu_bar/File/New Page", "note-new.png")
        set_menu_icon(u, "/main_menu_bar/File/New Child Page", "note-new.png")
        set_menu_icon(u, "/main_menu_bar/File/New Folder", "folder-new.png")


    def get_ui(self):

        return ["""
<ui>
<menubar name="main_menu_bar">
  <menu action="File">
     <menuitem action="New Notebook"/>
     <menuitem action="New Page"/>
     <menuitem action="New Child Page"/>
     <menuitem action="New Folder"/>
     <separator/>
     <menuitem action="Open Notebook"/>
     <menuitem action="Open Recent Notebook"/>
     <menuitem action="Reload Notebook"/>
     <menuitem action="Save Notebook"/>
     <menuitem action="Close Notebook"/>
     <separator/>
     <menu action="Export">
     </menu>
     <menu action="Import">
     </menu>
     <separator/>
     <placeholder name="File Extensions"/>
     <separator/>
     <menuitem action="Quit"/>
  </menu>
  <menu action="Edit">
    <menuitem action="Undo"/>
    <menuitem action="Redo"/>
    <separator/>
    <menuitem action="Cut"/>
    <menuitem action="Copy"/>
    <menuitem action="Paste"/>
    <separator/>
    <menuitem action="Attach File"/>
    <separator/>
    <placeholder name="Editor"/>
    <separator/>
    <menuitem action="Empty Trash"/>
  </menu>
  <menu action="Search">
    <menuitem action="Search All Notes"/>
    <placeholder name="Editor"/>
  </menu>
  <placeholder name="Editor"/>
  <menu action="View">
    <menuitem action="View Note in File Explorer"/>
    <menuitem action="View Note in Text Editor"/>
    <menuitem action="View Note in Web Browser"/>
    <menuitem action="Open File"/>
  </menu>
  <menu action="Go">
    <menuitem action="Back"/>
    <menuitem action="Forward"/>
    <separator/>
    <placeholder name="Viewer"/>
  </menu>
  <menu action="Options">
    <menuitem action="Spell Check"/>
    <separator/>
    <placeholder name="Viewer"/>
    <separator/>
    <menuitem action="Update Notebook Index"/>
    <separator/>
    <menuitem action="KeepNote Options"/>
  </menu>
  <menu action="Help">
    <menuitem action="View Error Log..."/>
    <menuitem action="Drag and Drop Test..."/>
    <separator/>
    <menuitem action="About"/>
  </menu>
</menubar>
</ui>
"""]

    
    def make_menubar(self):
        """Initialize the menu bar"""

        #===============================
        # ui manager

        self.actiongroup = gtk.ActionGroup('MainWindow')
        self.uimanager.insert_action_group(self.actiongroup, 0)

        # setup menus
        add_actions(self.actiongroup, self.get_actions())
        for s in self.get_ui():
            self.uimanager.add_ui_from_string(s)
        self.setup_menus(self.uimanager)


        # get spell check toggle
        self.spell_check_toggle = \
            self.uimanager.get_widget("/main_menu_bar/Options/Spell Check")
        self.spell_check_toggle.set_sensitive(
            self.viewer.editor.get_textview().can_spell_check())


        # return menu bar
        menubar = self.uimanager.get_widget('/main_menu_bar')
        return menubar
       
            

    
    def make_toolbar(self):
        
        toolbar = gtk.Toolbar()
        toolbar.set_orientation(gtk.ORIENTATION_HORIZONTAL)
        toolbar.set_style(gtk.TOOLBAR_ICONS)

        try:
            # NOTE: if this version of GTK doesn't have this size, then
            # ignore it
            toolbar.set_property("icon-size", gtk.ICON_SIZE_SMALL_TOOLBAR)
        except:
            pass
        
        toolbar.set_border_width(0)
        
        tips = gtk.Tooltips()
        tips.enable()
      

        # new folder
        button = gtk.ToolButton()
        if self.app.pref.use_stock_icons:
            button.set_stock_id(gtk.STOCK_DIRECTORY)
        else:
            button.set_icon_widget(get_resource_image("folder-new.png"))
        tips.set_tip(button, _("New Folder"))
        button.connect("clicked", lambda w: self.on_new_dir())
        toolbar.insert(button, -1)

        # new page
        button = gtk.ToolButton()
        if self.app.pref.use_stock_icons:
            button.set_stock_id(gtk.STOCK_NEW)
        else:
            button.set_icon_widget(get_resource_image("note-new.png"))
        tips.set_tip(button, _("New Page"))
        button.connect("clicked", lambda w: self.on_new_page())
        toolbar.insert(button, -1)

        # separator
        toolbar.insert(gtk.SeparatorToolItem(), -1)

        # back in history
        self.back_button = gtk.ToolButton()
        self.back_button.set_stock_id(gtk.STOCK_GO_BACK)
        tips.set_tip(self.back_button, "Back")
        self.back_button.connect("clicked", 
                                        lambda w: self._on_history(-1))
        toolbar.insert(self.back_button, -1)
        
        # forward in history
        self.forward_button = gtk.ToolButton()
        self.forward_button.set_stock_id(gtk.STOCK_GO_FORWARD)
        tips.set_tip(self.forward_button, "Forward")
        self.forward_button.connect("clicked", lambda w: self._on_history(1))
        toolbar.insert(self.forward_button, -1)


        # separator
        toolbar.insert(gtk.SeparatorToolItem(), -1)

        
        # insert editor toolbar
        self.viewer.make_toolbar(toolbar, tips, 
                                 self.app.pref.use_stock_icons,
                                 self.app.pref.use_minitoolbar)

        # separator
        spacer = gtk.SeparatorToolItem()
        spacer.set_draw(False)
        spacer.set_expand(True)
        toolbar.insert(spacer, -1)


        # search box
        item = gtk.ToolItem()
        self.search_box = gtk.Entry()
        #self.search_box.set_max_chars(30)
        self.search_box.connect("changed", self._on_search_box_text_changed)
        self.search_box.connect("activate",
                                lambda w: self.on_search_nodes())
        item.add(self.search_box)
        toolbar.insert(item, -1)

        self.search_box_list = gtk.ListStore(gobject.TYPE_STRING, 
                                             gobject.TYPE_STRING)
        self.search_box_completion = gtk.EntryCompletion()
        self.search_box_completion.connect("match-selected", 
                                           self._on_search_box_completion_match)
        self.search_box_completion.set_match_func(lambda c, k, i: True)
        self.search_box_completion.set_model(self.search_box_list)
        self.search_box_completion.set_text_column(0)
        self.search_box.set_completion(self.search_box_completion)
        self._ignore_text = False

        # search button
        self.search_button = gtk.ToolButton()
        self.search_button.set_stock_id(gtk.STOCK_FIND)
        tips.set_tip(self.search_button, _("Search All Notes"))
        self.search_button.connect("clicked",
                                   lambda w: self.on_search_nodes())
        toolbar.insert(self.search_button, -1)
        
                
        return toolbar


    def _on_search_box_text_changed(self, url_text):

        if not self._ignore_text:
            self.search_box_update_completion()

    def search_box_update_completion(self):

        text = unicode_gtk(self.search_box.get_text())
        
        self.search_box_list.clear()
        if len(text) > 0:
            results = self.viewer.get_notebook().search_node_titles(text)[:10]
            for nodeid, title in results:
                self.search_box_list.append([title, nodeid])

    def _on_search_box_completion_match(self, completion, model, iter):
        
        nodeid = model[iter][1]

        node = self.viewer.get_notebook().get_node_by_id(nodeid)
        if node:
            self.viewer.goto_node(node, False)




    def make_node_menu(self, widget, menu, control):
        """make list of menu options for nodes"""

        # new page
        item = gtk.ImageMenuItem(_("New _Page"))
        item.set_image(get_resource_image("note-new.png"))        
        item.connect("activate", lambda w: self.on_new_page(control))
        menu.append(item)
        item.show()


        # new child page 
        item = gtk.ImageMenuItem(_("New _Child Page"))
        item.set_image(get_resource_image("note-new.png"))
        item.connect("activate", lambda w: self.on_new_child_page(control))
        menu.append(item)
        item.show()

        
        # new folder
        item = gtk.ImageMenuItem(_("New _Folder"))
        item.set_image(get_resource_image("folder-new.png"))
        item.connect("activate", lambda w: self.on_new_dir(control))
        menu.append(item)
        item.show()
        

        # attach file
        item = gtk.ImageMenuItem(gtk.STOCK_ADD)
        item.child.set_label(_("_Attach File"))
        item.connect("activate", lambda w: self.on_attach_file(control))
        menu.append(item)
        item.show()

        #=============================================================
        item = gtk.SeparatorMenuItem()
        menu.append(item)
        item.show()

        # treeview/delete node
        item = gtk.ImageMenuItem(gtk.STOCK_DELETE)
        item.connect("activate", lambda w: widget.on_delete_node())
        menu.append(item)
        item.show()

        # rename node
        item = gtk.ImageMenuItem(gtk.STOCK_EDIT)
        item.child.set_label(_("_Rename"))
        item.connect("activate", lambda w:
                     widget.edit_node(widget.get_selected_nodes()[0]))
        menu.add(item)
        item.show()
        

        # change icon
        item = gtk.ImageMenuItem(_("Change _Icon"))
        img = gtk.Image()
        img.set_from_file(lookup_icon_filename(None, u"folder-red.png"))
        item.set_image(img)
        menu.append(item)
        menu.iconmenu = IconMenu()
        menu.iconmenu.connect("set-icon",
                              lambda w, i: self.on_set_icon(i, u"", control))
        menu.iconmenu.new_icon.connect("activate",
                                       lambda w: self.on_new_icon(control))
        item.set_submenu(menu.iconmenu)
        item.show()
        

        #=============================================================
        item = gtk.SeparatorMenuItem()
        menu.append(item)
        item.show()


        # treeview/file explorer
        item = gtk.ImageMenuItem(gtk.STOCK_OPEN)
        item.child.set_label(_("View in File _Explorer"))
        item.connect("activate",
                     lambda w: self.on_view_node_external_app("file_explorer",
                                                              None,
                                                              control))
        menu.append(item)
        item.show()        

        # treeview/web browser
        item = gtk.ImageMenuItem(gtk.STOCK_OPEN)
        item.child.set_label(_("View in _Web Browser"))
        item.connect("activate",
                     lambda w: self.on_view_node_external_app("web_browser",
                                                              None,
                                                              control,
                                                              kind="page"))
        menu.append(item)
        item.show()        

        # treeview/text editor
        item = gtk.ImageMenuItem(gtk.STOCK_OPEN)
        item.child.set_label(_("View in _Text Editor"))
        item.connect("activate",
                     lambda w: self.on_view_node_external_app("text_editor",
                                                              None,
                                                              control,
                                                              kind="page"))
        menu.append(item)
        item.show()

        # treeview/Open File
        item = gtk.ImageMenuItem(gtk.STOCK_OPEN)
        item.child.set_label(_("Open _File"))
        item.connect("activate",
                     lambda w: self.on_view_node_external_app("file_launcher",
                                                              None,
                                                              control,
                                                              kind="file"))
        menu.append(item)
        item.show()
        

    def make_treeview_menu(self, treeview, menu):
        """treeview context menu"""

        menu.set_accel_group(self.accel_group)
        menu.set_accel_path(CONTEXT_MENU_ACCEL_PATH)
        
        self.make_node_menu(treeview, menu, "treeview")

        
    def make_listview_menu(self, listview, menu):
        """listview context menu"""

        menu.set_accel_group(self.accel_group)
        menu.set_accel_path(CONTEXT_MENU_ACCEL_PATH)

        # listview/view note
        item = gtk.ImageMenuItem(gtk.STOCK_GO_DOWN)
        #item.child.set_label("Go to _Note")
        item.child.set_markup_with_mnemonic(_("<b>Go to _Note</b>"))
        item.connect("activate",
                     lambda w: self.viewer.on_list_view_node(None, None))
        menu.append(item)
        item.show()

        # listview/view note
        item = gtk.ImageMenuItem(gtk.STOCK_GO_UP)
        item.child.set_label(_("Go to _Parent Note"))
        item.connect("activate",
                     lambda w: self.viewer.on_list_view_parent_node())
        menu.append(item)
        item.show()

        item = gtk.SeparatorMenuItem()
        menu.append(item)
        item.show()

        self.make_node_menu(listview, menu, "listview")



    def make_context_menus(self, viewer):
        """Initialize context menus"""        
        
        #menu = viewer.editor.get_textview().get_popup_menu()
        #menu.set_accel_group(self.accel_group)
        #menu.set_accel_path(CONTEXT_MENU_ACCEL_PATH)

        self.make_treeview_menu(viewer.treeview, viewer.treeview.menu)
        self.make_listview_menu(viewer.listview, viewer.listview.menu)

