# PiTiVi , Non-linear video editor
#
#       ui/mainwindow.py
#
# Copyright (c) 2005, Edward Hervey <bilboed@bilboed.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

"""
Main GTK+ window
"""

import os
import gtk
import gst
import time
import gobject

try:
    import gconf
except:
    have_gconf=False
else:
    have_gconf=True

import pitivi.instance as instance
import pitivi.configure as configure
from pitivi.projectsaver import ProjectSaver

from gettext import gettext as _

from timeline import TimelineWidget
from sourcefactories import SourceFactoriesWidget
from viewer import PitiviViewer
from pitivi.bin import SmartTimelineBin
from projectsettings import ProjectSettingsDialog
from pluginmanagerdialog import PluginManagerDialog
from pitivi.configure import pitivi_version, APPNAME
from glade import GladeWindow

from exportsettingswidget import ExportSettingsDialog

if have_gconf:
    D_G_INTERFACE = "/desktop/gnome/interface"

    for gconf_dir in (D_G_INTERFACE,):
        gconf.client_get_default ().add_dir (gconf_dir, gconf.CLIENT_PRELOAD_NONE)


class PitiviMainWindow(gtk.Window):
    """
    Pitivi's main window
    """


    def __init__(self):
        """ initialize with the Pitivi object """
        gst.log("Creating MainWindow")
        gtk.Window.__init__(self)

        self._createStockIcons()
        self._setActions()
        self._createUi()
        self.actions = None
        self.toggleactions = None
        self.actiongroup = None

        self.isFullScreen = False
        self.errorDialogBox = None

        instance.PiTiVi.connect("new-project-loaded", self._newProjectLoadedCb)
        instance.PiTiVi.connect("new-project-loading", self._newProjectLoadingCb)
        instance.PiTiVi.connect("closing-project", self._closingProjectCb)
        instance.PiTiVi.connect("new-project-failed", self._notProjectCb)
        instance.PiTiVi.current.connect("save-uri-requested", self._saveAsDialogCb)
        instance.PiTiVi.current.connect("confirm-overwrite", self._confirmOverwriteCb)
        instance.PiTiVi.playground.connect("error", self._playGroundErrorCb)
        instance.PiTiVi.current.sources.connect_after("file_added", self._sourcesFileAddedCb)

        self.show_all()

    def _encodingDialogDestroyCb(self, unused_dialog):
        instance.PiTiVi.gui.set_sensitive(True)

    def _recordCb(self, unused_button):
        # pause timeline !
        instance.PiTiVi.playground.pause()

        win = EncodingDialog(instance.PiTiVi.current)
        win.window.connect("destroy", self._encodingDialogDestroyCb)
        instance.PiTiVi.gui.set_sensitive(False)
        win.show()

    def _timelineDurationChangedCb(self, unused_composition, unused_start,
                                   duration):
        if not isinstance(instance.PiTiVi.playground.current, SmartTimelineBin):
            return
        self.render_button.set_sensitive((duration > 0) and True or False)
        if duration > 0 :
            gobject.idle_add(self.timeline.simpleview._displayTimeline)

    def _currentPlaygroundChangedCb(self, playground, smartbin):
        if smartbin == playground.default:
            self.render_button.set_sensitive(False)
        else:
            if isinstance(smartbin, SmartTimelineBin):
                gst.info("switching to Timeline, setting duration to %s" %
                         (gst.TIME_ARGS(smartbin.project.timeline.videocomp.duration)))
                smartbin.project.timeline.videocomp.connect("start-duration-changed",
                                                            self._timelineDurationChangedCb)
                if smartbin.project.timeline.videocomp.duration > 0:
                    self.render_button.set_sensitive(True)
                    gobject.idle_add(self.timeline.simpleview._displayTimeline)
                else:
                    self.render_button.set_sensitive(False)
            else:
                self.render_button.set_sensitive(False)

    def _createStockIcons(self):
        """ Creates the pitivi-only stock icons """
        gtk.stock_add([
                ('pitivi-advanced-mode', 'Advanced Mode', 0, 0, 'pitivi'),
                ('pitivi-render', 'Render', 0, 0, 'pitivi')
                ])
        factory = gtk.IconFactory()
        pixbuf = gtk.gdk.pixbuf_new_from_file(
            configure.get_pixmap_dir() + "/pitivi-advanced-24.png")
        iconset = gtk.IconSet(pixbuf)
        factory.add('pitivi-advanced-mode', iconset)
        pixbuf = gtk.gdk.pixbuf_new_from_file(
            configure.get_pixmap_dir() + "/pitivi-render-24.png")
        iconset = gtk.IconSet(pixbuf)
        factory.add('pitivi-render', iconset)
        factory.add_default()


    def _setActions(self):
        """ sets up the GtkActions """
        self.actions = [
            ("NewProject", gtk.STOCK_NEW, None,
             None, _("Create a new project"), self._newProjectMenuCb),
            ("OpenProject", gtk.STOCK_OPEN, None,
             None, _("Open an existing project"), self._openProjectCb),
            ("SaveProject", gtk.STOCK_SAVE, None,
             None, _("Save the current project"), self._saveProjectCb),
            ("SaveProjectAs", gtk.STOCK_SAVE_AS, None,
             None, _("Save the current project"), self._saveProjectAsCb),
            ("ProjectSettings", gtk.STOCK_PROPERTIES, _("Project settings"),
             None, _("Edit the project settings"), self._projectSettingsCb),
            ("ImportSources", gtk.STOCK_ADD, _("_Import clips..."),
             None, _("Import clips to use"), self._importSourcesCb),
            ("ImportSourcesFolder", gtk.STOCK_ADD,
             _("_Import folder of clips..."), None,
             _("Import folder of clips to use"), self._importSourcesFolderCb),
            ("RenderProject", 'pitivi-render' , _("_Render project"),
             None, _("Render project"), self._recordCb),
            ("PluginManager", gtk.STOCK_PREFERENCES ,
             _("_Plugins..."),
             None, _("Manage plugins"), self._pluginManagerCb),
            ("Quit", gtk.STOCK_QUIT, None, None, None, self._quitCb),
            ("About", gtk.STOCK_ABOUT, None, None,
             _("Information about %s") % APPNAME, self._aboutCb),
            ("File", None, _("_File")),
            ("Edit", None, _("_Edit")),
            ("View", None, _("_View")),
            ("Help", None, _("_Help"))
        ]

        self.toggleactions = [
            ("AdvancedView", 'pitivi-advanced-mode', _("Advanced vie_w"),
             None, _("Switch to advanced view"), self._advancedViewCb),
            ("FullScreen", gtk.STOCK_FULLSCREEN, None, None,
             _("View the main window on the whole screen"), self._fullScreenCb)
        ]

        self.actiongroup = gtk.ActionGroup("mainwindow")
        self.actiongroup.add_actions(self.actions)
        self.actiongroup.add_toggle_actions(self.toggleactions)

        # deactivating non-functional actions
        # FIXME : reactivate them
        for action in self.actiongroup.list_actions():
            if action.get_name() == "RenderProject":
                self.render_button = action
            elif action.get_name() == "AdvancedView":
                if not instance.PiTiVi.settings.advancedModeEnabled:
                    action.set_visible(False)
            elif action.get_name() in [
                "ProjectSettings", "Quit", "File", "Edit", "Help",
                "About", "View", "FullScreen", "ImportSources",
                "ImportSourcesFolder", "AdvancedView", "PluginManager"]:
                action.set_sensitive(True)
            elif action.get_name() in ["SaveProject", "SaveProjectAs",
                    "NewProject", "OpenProject"]:
                if not instance.PiTiVi.settings.fileSupportEnabled:
                    action.set_sensitive(False)
            else:
                action.set_sensitive(False)

        self.uimanager = gtk.UIManager()
        self.add_accel_group(self.uimanager.get_accel_group())
        self.uimanager.insert_action_group(self.actiongroup, 0)
        self.uimanager.add_ui_from_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "actions.xml"))

        self.connect_after("key-press-event", self._keyPressEventCb)

    def _createUi(self):
        """ Create the graphical interface """
        self.set_title("%s v%s" % (APPNAME, pitivi_version))
        self.set_geometry_hints(min_width=800, min_height=600)

        self.connect("destroy", self._destroyCb)

        vbox = gtk.VBox(False)
        self.add(vbox)

        self.menu = self.uimanager.get_widget("/MainMenuBar")
        vbox.pack_start(self.menu, expand=False)

        self.toolbar = self.uimanager.get_widget("/MainToolBar")

        vbox.pack_start(self.toolbar, expand=False)


        vpaned = gtk.VPaned()
        vbox.pack_start(vpaned)

        self.timeline = TimelineWidget()
        self.timeline.showSimpleView()
        timelineframe = gtk.Frame()
        timelineframe.add(self.timeline)
        vpaned.pack2(timelineframe, resize=False, shrink=False)

        hpaned = gtk.HPaned()
        vpaned.pack1(hpaned, resize=True, shrink=False)

        # source-and-effects list
        self.sourcefactories = SourceFactoriesWidget()

        # Viewer
        self.viewer = PitiviViewer()

        instance.PiTiVi.playground.connect("current-changed", self._currentPlaygroundChangedCb)

        hpaned.pack1(self.sourcefactories, resize=False, shrink=False)
        hpaned.pack2(self.viewer, resize=True, shrink=False)

        #application icon
        self.set_icon_from_file(configure.get_global_pixmap_dir() + "/pitivi.png")

    def toggleFullScreen(self):
        """ Toggle the fullscreen mode of the application """
        if not self.isFullScreen:
            self.viewer.window.fullscreen()
            self.isFullScreen = True
        else:
            self.viewer.window.unfullscreen()
            self.isFullScreen = False

    ## PlayGround callback

    def _errorMessageResponseCb(self, dialogbox, unused_response):
        dialogbox.hide()
        dialogbox.destroy()
        self.errorDialogBox = None

    def _playGroundErrorCb(self, unused_playground, error, detail):
        if self.errorDialogBox:
            return
        self.errorDialogBox = gtk.MessageDialog(None, gtk.DIALOG_MODAL,
                                                gtk.MESSAGE_ERROR,
                                                gtk.BUTTONS_OK,
                                                None)
        self.errorDialogBox.set_markup("<b>%s</b>" % error)
        self.errorDialogBox.connect("response", self._errorMessageResponseCb)
        if detail:
            self.errorDialogBox.format_secondary_text(detail)
        self.errorDialogBox.show()


    ## Project source list callbacks

    def _sourcesFileAddedCb(self, unused_sources, unused_factory):
        if len(self.sourcefactories.sourcelist.storemodel) == 1 and not len(instance.PiTiVi.current.timeline.videocomp):
            self.timeline.simpleview._displayTimeline(False)


    ## UI Callbacks

    def _destroyCb(self, unused_widget, data=None):
        instance.PiTiVi.shutdown()


    def _keyPressEventCb(self, unused_widget, event):
        if gtk.gdk.keyval_name(event.keyval) in ['f', 'F', 'F11']:
            self.toggleFullScreen()

    ## Toolbar/Menu actions callback

    def _newProjectMenuCb(self, unused_action):
        instance.PiTiVi.newBlankProject()

    def _openProjectCb(self, unused_action):
        chooser = gtk.FileChooserDialog(_("Open File ..."),
            self,
            action=gtk.FILE_CHOOSER_ACTION_OPEN,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        chooser.set_select_multiple(False)
        formats = ProjectSaver.listFormats()
        default = gtk.FileFilter()
        default.set_name("All")
        default.add_pattern("*")
        chooser.add_filter(default)
        for format in formats:
            filt = gtk.FileFilter()
            filt.set_name(format[0])
            for ext in format[1]:
                filt.add_pattern("*%s" % ext)
            chooser.add_filter(filt)

        response = chooser.run()

        if response == gtk.RESPONSE_OK:
            path = chooser.get_filename()
            instance.PiTiVi.loadProject(filepath = path)
        chooser.destroy()
        return True

    def _saveProjectCb(self, unused_action):
        instance.PiTiVi.current.save()

    def _saveProjectAsCb(self, unused_action):
        instance.PiTiVi.current.saveAs()

    def _projectSettingsCb(self, unused_action):
        l = ProjectSettingsDialog(self, instance.PiTiVi.current)
        l.show()

    def _quitCb(self, unused_action):
        instance.PiTiVi.shutdown()

    def _fullScreenCb(self, unused_action):
        self.toggleFullScreen()

    def _advancedViewCb(self, action):
        if action.get_active():
            self.timeline.showComplexView()
        else:
            self.timeline.showSimpleView()

    def _aboutResponseCb(self, dialog, unused_response):
        dialog.destroy()

    def _aboutCb(self, unused_action):
        abt = gtk.AboutDialog()
        abt.set_name(APPNAME)
        abt.set_version("v%s" % pitivi_version)
        abt.set_website("http://www.pitivi.org/")
        authors = ["Edward Hervey <bilboed@bilboed.com>","",_("Contributors:"),
                   "Christophe Sauthier <christophe.sauthier@gmail.com> (i18n)",
                   "Laszlo Pandy <laszlok2@gmail.com> (UI)",
                   "Ernst Persson  <ernstp@gmail.com>",
                   "Richard Boulton <richard@tartarus.org>",
                   "Thibaut Girka <thibaut.girka@free.fr> (UI)",
                   "Jeff Fortin <nekohayo@gmail.com> (UI)",
                   "Johan Dahlin <jdahlin@async.com.br> (UI)",
                   "Brandon Lewis <brandon_lewis@berkeley.edu> (UI)",
                   "Luca Della Santina <dellasantina@farm.unipi.it>",
                   "Thijs Vermeir <thijsvermeir@gmail.com>"]
        abt.set_authors(authors)
        abt.set_license(_("GNU Lesser General Public License\nSee http://www.gnu.org/copyleft/lesser.html for more details"))
        abt.set_icon_from_file(configure.get_global_pixmap_dir() + "/pitivi.png")
        abt.connect("response", self._aboutResponseCb)
        abt.show()

    def _importSourcesCb(self, unused_action):
        self.sourcefactories.sourcelist.showImportSourcesDialog()

    def _importSourcesFolderCb(self, unused_action):
        self.sourcefactories.sourcelist.showImportSourcesDialog(True)

    def _pluginManagerCb(self, unused_action):
        PluginManagerDialog(instance.PiTiVi.plugin_manager)

    ## PiTiVi main object callbacks

    def _newProjectLoadedCb(self, pitivi, project):
        gst.log("A NEW project is loaded, update the UI!")
        # ungrey UI
        self.set_sensitive(True)

    def _newProjectLoadingCb(self, pitivi, project):
        gst.log("A NEW project is being loaded, deactivate UI")
        # grey UI
        self.set_sensitive(False)

    def _closingProjectCb(self, pitivi, project):
        if not project.hasUnsavedModifications():
            return True

        dialog = gtk.MessageDialog(
            self,
            gtk.DIALOG_MODAL,
            gtk.MESSAGE_QUESTION,
            gtk.BUTTONS_YES_NO,
            _("The project has unsaved changes. Do you wish to close the project?"))
        response = dialog.run()
        dialog.destroy()
        if response == gtk.RESPONSE_YES:
            return True
        return False

    def _notProjectCb(self, pitivi, reason, uri):
        # ungrey UI
        dialog = gtk.MessageDialog(self,
            gtk.DIALOG_MODAL,
            gtk.MESSAGE_ERROR,
            gtk.BUTTONS_OK,
            _("PiTiVi is unable to load file \"%s\": %s") %
                (uri, reason))
        dialog.set_title(_("Error Loading File"))
        dialog.run()
        dialog.destroy()
        self.set_sensitive(True)

    ## PiTiVi current project callbacks

    def _confirmOverwriteCb(self, unused_project, uri):
        message = _("Do you wish to overwrite existing file \"%s\"?") %\
                 gst.uri_get_location(uri)

        dialog = gtk.MessageDialog(self,
            gtk.DIALOG_MODAL,
            gtk.MESSAGE_WARNING,
            gtk.BUTTONS_YES_NO,
            message)

        dialog.set_title(_("Overwrite Existing File?"))
        response = dialog.run()
        dialog.destroy()
        if response == gtk.RESPONSE_YES:
            return True
        return False

    def _saveAsDialogCb(self, project):
        chooser = gtk.FileChooserDialog(_("Save As..."),
            self,
            action=gtk.FILE_CHOOSER_ACTION_SAVE,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
            gtk.STOCK_SAVE, gtk.RESPONSE_OK))

        chooser.set_select_multiple(False)
        chooser.set_current_name(_("Untitled.pptv"))
        chooser.set_default_response(gtk.RESPONSE_CANCEL)
        formats = ProjectSaver.listFormats()
        default = gtk.FileFilter()
        default.set_name(_("Detect Automatically"))
        default.add_pattern("*")
        chooser.add_filter(default)
        for format in formats:
            filt = gtk.FileFilter()
            filt.set_name(format[0])
            for ext in format[1]:
                filt.add_pattern("*.%s" % ext)
            chooser.add_filter(filt)

        response = chooser.run()

        if response == gtk.RESPONSE_OK:
            # need to do this to work around bug in gst.uri_construct
            # which escapes all /'s in path!
            uri = "file://" + chooser.get_filename()
            format = chooser.get_filter().get_name()
            if format == _("Detect Automatically"):
                format = None
            project.setUri(uri, format)
            chooser.destroy()
            return True
        chooser.destroy()
        return False


class EncodingDialog(GladeWindow):
    """ Encoding dialog box """
    glade_file = "encodingdialog.glade"

    def __init__(self, project):
        GladeWindow.__init__(self)
        self.project = project
        self.bin = project.getBin()
        self.bus = self.bin.get_bus()
        self.bus.add_signal_watch()
        self.eosid = self.bus.connect("message::eos", self._eosCb)
        self.outfile = None
        self.progressbar = self.widgets["progressbar"]
        self.cancelbutton = self.widgets["cancelbutton"]
        self.recordbutton = self.widgets["recordbutton"]
        self.recordbutton.set_sensitive(False)
        self.positionhandler = 0
        self.rendering = False
        self.settings = project.getSettings()
        self.timestarted = 0
        self.vinfo = self.widgets["videoinfolabel"]
        self.ainfo = self.widgets["audioinfolabel"]
        self.window.set_icon_from_file(configure.get_pixmap_dir() + "/pitivi-render-16.png")
        self._displaySettings()

    def _displaySettings(self):
        self.vinfo.set_markup(self.settings.getVideoDescription())
        self.ainfo.set_markup(self.settings.getAudioDescription())

    def _fileButtonClickedCb(self, button):

        dialog = gtk.FileChooserDialog(title=_("Choose file to render to"),
                                       parent=self.window,
                                       buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT,
                                                gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT),
                                       action=gtk.FILE_CHOOSER_ACTION_SAVE)
        if self.outfile:
            dialog.set_current_name(self.outfile)
        res = dialog.run()
        dialog.hide()
        if res == gtk.RESPONSE_ACCEPT:
            self.outfile = dialog.get_uri()
            button.set_label(os.path.basename(self.outfile))
            self.recordbutton.set_sensitive(True)
            self.progressbar.set_text("")
        dialog.destroy()

    def _positionCb(self, unused_playground, unused_smartbin, position):
        timediff = time.time() - self.timestarted
        self.progressbar.set_fraction(float(min(position, self.bin.length)) / float(self.bin.length))
        if timediff > 5.0 and position:
            # only display ETA after 5s in order to have enough averaging and
            # if the position is non-null
            totaltime = (timediff * float(self.bin.length) / float(position)) - timediff
            self.progressbar.set_text(_("Finished in %dm%ds") % (int(totaltime) / 60,
                                                              int(totaltime) % 60))

    def _recordButtonClickedCb(self, unused_button):
        if self.outfile and not self.rendering:
            if self.bin.record(self.outfile, self.settings):
                self.timestarted = time.time()
                self.positionhandler = instance.PiTiVi.playground.connect('position', self._positionCb)
                self.rendering = True
                self.cancelbutton.set_label("gtk-cancel")
                self.progressbar.set_text(_("Rendering"))
                self.recordbutton.set_sensitive(False)
            else:
                self.progressbar.set_text(_("Couldn't start rendering"))

    def _settingsButtonClickedCb(self, unused_button):
        dialog = ExportSettingsDialog(self.settings)
        res = dialog.run()
        dialog.hide()
        if res == gtk.RESPONSE_ACCEPT:
            self.settings = dialog.getSettings()
            self._displaySettings()
        dialog.destroy()

    def do_destroy(self):
        gst.debug("cleaning up...")
        self.bus.remove_signal_watch()
        gobject.source_remove(self.eosid)

    def _eosCb(self, unused_bus, unused_message):
        self.rendering = False
        if self.positionhandler:
            instance.PiTiVi.playground.disconnect(self.positionhandler)
            self.positionhandler = 0
        self.progressbar.set_text(_("Rendering Complete"))
        self.progressbar.set_fraction(1.0)
        self.recordbutton.set_sensitive(True)
        self.cancelbutton.set_label("gtk-close")

    def _cancelButtonClickedCb(self, unused_button):
        self.bin.stopRecording()
        if self.positionhandler:
            instance.PiTiVi.playground.disconnect(self.positionhandler)
            self.positionhandler = 0
        instance.PiTiVi.playground.pause()
        self.destroy()
