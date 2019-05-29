
# AviaNZ_batch.py
#
# This is the proceesing class for the batch AviaNZ interface
# Version 1.3 23/10/18
# Authors: Stephen Marsland, Nirosha Priyadarshani, Julius Juodakis

#    AviaNZ birdsong analysis program
#    Copyright (C) 2017--2018

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
import os, re, platform, fnmatch, sys

from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QMessageBox, QMainWindow, QLabel, QPlainTextEdit, QPushButton, QTimeEdit, QSpinBox, QListWidget, QDesktopWidget, QApplication, QComboBox, QLineEdit, QSlider, QListWidgetItem
from PyQt5.QtMultimedia import QAudioFormat
from PyQt5.QtCore import Qt, QDir

import wavio
import librosa
import numpy as np

from pyqtgraph.Qt import QtGui
from pyqtgraph.dockarea import *
import pyqtgraph as pg

import SignalProc
import Segment
import WaveletSegment
import SupportClasses
import Dialogs

import json, copy


class AviaNZ_batchProcess(QMainWindow):
    # Main class for batch processing

    def __init__(self, root=None, configdir='', minSegment=50):
        # Allow the user to browse a folder and push a button to process that folder to find a target species
        # and sets up the window.
        super(AviaNZ_batchProcess, self).__init__()
        self.root = root
        self.dirName=[]

        # read config and filters from user location
        self.configfile = os.path.join(configdir, "AviaNZconfig.txt")
        self.ConfigLoader = SupportClasses.ConfigLoader()
        self.config = self.ConfigLoader.config(self.configfile)
        self.saveConfig = True

        self.filtersDir = os.path.join(configdir, self.config['FiltersDir'])
        self.FilterFiles = self.ConfigLoader.filters(self.filtersDir)

        # Make the window and associated widgets
        QMainWindow.__init__(self, root)

        self.statusBar().showMessage("Processing file Current/Total")

        self.setWindowTitle('AviaNZ - Batch Processing')
        self.setWindowIcon(QIcon('img/Avianz.ico'))
        self.createMenu()
        self.createFrame()
        self.center()

    def createFrame(self):
        # Make the window and set its size
        self.area = DockArea()
        self.setCentralWidget(self.area)
        self.setFixedSize(870,550)

        # Make the docks
        self.d_detection = Dock("Automatic Detection",size=(600,550))
        self.d_files = Dock("File list", size=(270, 550))

        self.area.addDock(self.d_detection,'right')
        self.area.addDock(self.d_files, 'left')

        self.w_browse = QPushButton("  &Browse Folder")
        self.w_browse.setToolTip("Can select a folder with sub folders to process")
        self.w_browse.setFixedHeight(50)
        self.w_browse.setStyleSheet('QPushButton {background-color: #A3C1DA; font-weight: bold; font-size:14px}')
        self.w_dir = QPlainTextEdit()
        self.w_dir.setFixedHeight(50)
        self.w_dir.setPlainText('')
        self.w_dir.setToolTip("The folder being processed")
        self.d_detection.addWidget(self.w_dir,row=0,col=1,colspan=2)
        self.d_detection.addWidget(self.w_browse,row=0,col=0)

        self.w_speLabel1 = QLabel("  Select Species")
        self.d_detection.addWidget(self.w_speLabel1,row=1,col=0)
        self.w_spe1 = QComboBox()
        # read filter list, replace subsp marks with brackets
        spp = [*self.FilterFiles]
        for sp in spp:
            ind = sp.find('>')
            if ind > -1:
                sp = sp[:ind] + ' (' + sp[ind+1:] + ')'
        spp.insert(0, "All species")
        self.w_spe1.addItems(spp)
        self.d_detection.addWidget(self.w_spe1,row=1,col=1,colspan=2)

        self.w_resLabel = QLabel("  Time Resolution in Excel Output (secs)")
        self.d_detection.addWidget(self.w_resLabel, row=2, col=0)
        self.w_res = QSpinBox()
        self.w_res.setRange(1,600)
        self.w_res.setSingleStep(5)
        self.w_res.setValue(60)
        self.d_detection.addWidget(self.w_res, row=2, col=1, colspan=2)

        self.w_timeWindow = QLabel("  Choose Time Window (from-to)")
        self.d_detection.addWidget(self.w_timeWindow, row=4, col=0)
        self.w_timeStart = QTimeEdit()
        self.w_timeStart.setDisplayFormat('hh:mm:ss')
        self.d_detection.addWidget(self.w_timeStart, row=4, col=1)
        self.w_timeEnd = QTimeEdit()
        self.w_timeEnd.setDisplayFormat('hh:mm:ss')
        self.d_detection.addWidget(self.w_timeEnd, row=4, col=2)

        self.w_processButton = QPushButton("&Process Folder")
        self.w_processButton.clicked.connect(self.detect)
        self.d_detection.addWidget(self.w_processButton,row=11,col=2)
        self.w_processButton.setStyleSheet('QPushButton {background-color: #A3C1DA; font-weight: bold; font-size:14px}')

        self.w_browse.clicked.connect(self.browse)

        self.w_files = pg.LayoutWidget()
        self.d_files.addWidget(self.w_files)
        self.w_files.addWidget(QLabel('View Only'), row=0, col=0)
        self.w_files.addWidget(QLabel('use Browse Folder to choose data for processing'), row=1, col=0)
        # self.w_files.addWidget(QLabel(''), row=2, col=0)
        # List to hold the list of files
        self.listFiles = QListWidget()
        self.listFiles.setMinimumWidth(150)
        self.listFiles.itemDoubleClicked.connect(self.listLoadFile)
        self.w_files.addWidget(self.listFiles, row=2, col=0)

        self.show()

    def createMenu(self):
        """ Create the basic menu.
        """

        helpMenu = self.menuBar().addMenu("&Help")
        helpMenu.addAction("Help", self.showHelp,"Ctrl+H")
        aboutMenu = self.menuBar().addMenu("&About")
        aboutMenu.addAction("About", self.showAbout,"Ctrl+A")
        aboutMenu = self.menuBar().addMenu("&Quit")
        aboutMenu.addAction("Quit", self.quitPro,"Ctrl+Q")

    def showAbout(self):
        """ Create the About Message Box. Text is set in SupportClasses.MessagePopup"""
        msg = SupportClasses.MessagePopup("a", "About", ".")
        msg.exec_()
        return

    def showHelp(self):
        """ Show the user manual (a pdf file)"""
        # TODO: manual is not distributed as pdf now
        import webbrowser
        # webbrowser.open_new(r'file://' + os.path.realpath('./Docs/AviaNZManual.pdf'))
        webbrowser.open_new(r'http://avianz.net/docs/AviaNZManual_v1.1.pdf')

    def quitPro(self):
        """ quit program
        """
        QApplication.quit()

    def center(self):
        # geometry of the main window
        qr = self.frameGeometry()
        # center point of screen
        cp = QDesktopWidget().availableGeometry().center()
        # move rectangle's center point to screen's center point
        qr.moveCenter(cp)
        # top left of rectangle becomes top left of window centering it
        self.move(qr.topLeft())

    def cleanStatus(self):
        self.statusBar().showMessage("Processing file Current/Total")

    def browse(self):
        if self.dirName:
            self.dirName = QtGui.QFileDialog.getExistingDirectory(self,'Choose Folder to Process',str(self.dirName))
        else:
            self.dirName = QtGui.QFileDialog.getExistingDirectory(self,'Choose Folder to Process')
        #print("Dir:", self.dirName)
        self.w_dir.setPlainText(self.dirName)
        self.w_dir.setReadOnly(True)
        self.fillFileList(self.dirName)


    # from memory_profiler import profile
    # fp = open('memory_profiler_wp.log', 'w+')
    # @profile(stream=fp)
    def detect(self, minLen=5):
        # check if folder was selected:
        if not self.dirName:
            msg = SupportClasses.MessagePopup("w", "Select Folder", "Please select a folder to process!")
            msg.exec_()
            return

        self.species=self.w_spe1.currentText()
        if self.species == "All species":
            self.method = "Default"
        else:
            self.method = "Wavelets"

        # directory found, so find any .wav files
        total=0
        for root, dirs, files in os.walk(str(self.dirName)):
            for filename in files:
                if filename.endswith('.wav'):
                    total = total+1

        # LOG FILE is read here
        # note: important to log all analysis settings here
        self.log = SupportClasses.Log(os.path.join(self.dirName, 'LastAnalysisLog.txt'),
                                self.species, [self.method, self.w_res.value()])

        # Ask for RESUME CONFIRMATION here
        confirmedResume = QMessageBox.Cancel
        if self.log.possibleAppend:
            if len(self.log.filesDone) < total:
                text = "Previous analysis found in this folder (analyzed " + str(len(self.log.filesDone)) + " out of " + str(total) + " files in this folder).\nWould you like to resume that analysis?"
                msg = SupportClasses.MessagePopup("t", "Resume previous batch analysis?", text)
                msg.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
                confirmedResume = msg.exec_()
            else:
                print("All files appear to have previous analysis results")
                msg = SupportClasses.MessagePopup("d", "Already processed", "All files have previous analysis results")
                msg.exec_()
        else:
            confirmedResume = QMessageBox.No

        if confirmedResume == QMessageBox.Cancel:
            # catch unclean (Esc) exits
            return
        elif confirmedResume == QMessageBox.No:
            # work on all files
            self.filesDone = []
        elif confirmedResume == QMessageBox.Yes:
            # ignore files in log
            self.filesDone = self.log.filesDone

        # Ask for FINAL USER CONFIRMATION here
        cnt = len(self.filesDone)
        confirmedLaunch = QMessageBox.Cancel

        text = "Species: " + self.species + ", resolution: "+ str(self.w_res.value()) + ", method: " + self.method + ".\nNumber of files to analyze: " + str(total) + ", " + str(cnt) + " done so far.\n"
        text += "Output stored in " + self.dirName + "/DetectionSummary_*.xlsx.\n"
        text += "Log file stored in " + self.dirName + "/LastAnalysisLog.txt.\n"
        text = "Analysis will be launched with these settings:\n" + text + "\nConfirm?"

        msg = SupportClasses.MessagePopup("t", "Launch batch analysis", text)
        msg.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        confirmedLaunch = msg.exec_()

        if confirmedLaunch == QMessageBox.Cancel:
            print("Analysis cancelled")
            return

        # update log: delete everything (by opening in overwrite mode),
        # reprint old headers,
        # print current header (or old if resuming),
        # print old file list if resuming.
        self.log.file = open(self.log.file, 'w')
        if self.species != "All species":
            self.log.reprintOld()
            # else single-sp runs should be deleted anyway
        if confirmedResume == QMessageBox.No:
            self.log.appendHeader(header=None, species=self.log.species, settings=self.log.settings)
        elif confirmedResume == QMessageBox.Yes:
            self.log.appendHeader(self.log.currentHeader, self.log.species, self.log.settings)
            for f in self.log.filesDone:
                self.log.appendFile(f)

        # delete old results (xlsx)
        # ! WARNING: any Detection...xlsx files will be DELETED,
        # ! ANYWHERE INSIDE the specified dir, recursively
        for root, dirs, files in os.walk(str(self.dirName)):
            for filename in files:
                if fnmatch.fnmatch(filename, '*DetectionSummary_*.xlsx'):
                    print("Removing excel file %s" % filename)
                    os.remove(os.path.join(root, filename))

        # MAIN PROCESSING starts here
        # Read the time window to process
        timeWindow_s = self.w_timeStart.time().hour() * 3600 + self.w_timeStart.time().minute() * 60 + self.w_timeStart.time().second()
        timeWindow_e = self.w_timeEnd.time().hour() * 3600 + self.w_timeEnd.time().minute() * 60 + self.w_timeEnd.time().second()
        with pg.BusyCursor():
            for root, dirs, files in os.walk(str(self.dirName)):
                for filename in files:
                    self.filename = os.path.join(root, filename)
                    self.segments = []
                    newSegments = []
                    if self.filename in self.filesDone:
                        # skip the processing, but still need to update excel:
                        print("File %s processed previously, skipping" % filename)
                        # TODO: check the following line, if skip no need to load .wav (except for getting file length for sheet3?)
                        # TODO: Instead can we keep length of the recording as part of the meta info in [-1 ... -1]
                        self.loadFile(wipe=(self.species == "All species"))
                        DOCRecording = re.search('(\d{6})_(\d{6})', filename)
                        if DOCRecording:
                            startTime = DOCRecording.group(2)
                            sTime = int(startTime[:2]) * 3600 + int(startTime[2:4]) * 60 + int(startTime[4:6])
                        else:
                            sTime = 0
                        if self.species == 'All species':
                            out = SupportClasses.exportSegments(segments=self.segments, species=[], startTime=sTime, dirName=self.dirName, filename=self.filename, datalength=self.datalength, sampleRate=self.sampleRate,method=self.method, resolution=self.w_res.value(), operator="Auto", batch=True)
                        else:
                            out = SupportClasses.exportSegments(segments=self.segments, species=[self.species], startTime=sTime, dirName=self.dirName, filename=self.filename, datalength=self.datalength, sampleRate=self.sampleRate,method=self.method, resolution=self.w_res.value(), operator="Auto", batch=True)
                        out.excel()
                        continue

                    if filename.endswith('.wav'):
                        cnt = cnt+1
                        # check if file not empty
                        print("Processing file " + str(cnt) + "/" + str(total))
                        print("Opening file %s" % filename)
                        self.statusBar().showMessage("Processing file " + str(cnt) + "/" + str(total))
                        if os.stat(self.filename).st_size < 100:
                            print("Skipping empty file")
                            self.log.appendFile(self.filename)
                            continue

                        # test the selected time window if it is a doc recording
                        inWindow = False

                        DOCRecording = re.search('(\d{6})_(\d{6})', filename)
                        if DOCRecording:
                            startTime = DOCRecording.group(2)
                            sTime = int(startTime[:2]) * 3600 + int(startTime[2:4]) * 60 + int(startTime[4:6])
                            if timeWindow_s == timeWindow_e:
                                inWindow = True
                            elif timeWindow_s < timeWindow_e:
                                if sTime >= timeWindow_s and sTime <= timeWindow_e:
                                    inWindow = True
                                else:
                                    inWindow = False
                            else:
                                if sTime >= timeWindow_s or sTime <= timeWindow_e:
                                    inWindow = True
                                else:
                                    inWindow = False
                        else:
                            sTime=0
                            inWindow = True

                        if DOCRecording and not inWindow:
                            print("Skipping out-of-time-window recording")
                            self.log.appendFile(self.filename)
                            continue

                        # ALL SYSTEMS GO: process this file
                        print("Loading file...")
                        self.loadFile(wipe=(self.species == "All species"))
                        print("Creating wavelet packet...")
                        if self.species != 'All species':
                            # wipe same species:
                            self.segments[:] = [s for s in self.segments if self.species not in s[4] and self.species+'?' not in s[4]]
                            self.speciesData = json.load(open(os.path.join(self.filtersDir, self.species+'.txt')))
                            ws = WaveletSegment.WaveletSegment(self.speciesData, 'dmey2')
                            # 'recaa' mode
                            newSegments = ws.waveletSegment(data=self.audiodata, sampleRate=self.sampleRate,
                                                            d=False, f=True, wpmode="new")
                            print('Segments after wavelet seg: ', newSegments)
                        else:
                            # wipe all segments:
                            self.segments = []
                            self.seg = Segment.Segment(self.audiodata, self.sgRaw, self.sp, self.sampleRate)
                            newSegments=self.seg.bestSegments()

                        # post process to remove short segments, wind, rain, and use F0 check.
                        if self.species == 'All species':
                            post = SupportClasses.postProcess(audioData=self.audiodata, sampleRate=self.sampleRate,
                                                              segments=newSegments, spInfo={})
                            post.wind()
                            post.rainClick()
                        else:
                            post = SupportClasses.postProcess(audioData=self.audiodata, sampleRate=self.sampleRate,
                                                              segments=newSegments, spInfo=self.speciesData)
                            #   post.short()  # TODO: keep 'deleteShort' in filter file?
                            if self.speciesData['Wind']:
                                pass
                                # post.wind() - omitted in sppSpecific cases
                                # print('After wind: ', post.segments)
                            if self.speciesData['Rain']:
                                pass
                                # post.rainClick() - omitted in sppSpecific cases
                                # print('After rain: ', post.segments)
                            if self.speciesData['F0']:
                                post.fundamentalFrq()
                                # print('After ff: ', post.segments)
                        newSegments = post.segments
                        print('Segments after post pro: ', newSegments)

                        # Save the excel and the annotation
                        if self.species == 'All species':
                            out = SupportClasses.exportSegments(segments=[], segmentstoCheck=newSegments, species=[], startTime=sTime, dirName=self.dirName, filename=self.filename, datalength=self.datalength/self.sampleRate, sampleRate=self.sampleRate, method=self.method, resolution=self.w_res.value(), operator="Auto", batch=True)
                        else:
                            out = SupportClasses.exportSegments(segments=self.segments, segmentstoCheck=newSegments, species=[self.species], startTime=sTime, dirName=self.dirName, filename=self.filename, datalength=self.datalength/self.sampleRate, sampleRate=self.sampleRate, method=self.method, resolution=self.w_res.value(), operator="Auto", sampleRate_species=self.speciesData['SampleRate'], fRange=self.speciesData['FreqRange'], batch=True)
                        out.excel()
                        out.saveAnnotation()
                        # Log success for this file
                        self.log.appendFile(self.filename)
            self.log.file.close()
            self.statusBar().showMessage("Processed all %d files" % total)
            msg = SupportClasses.MessagePopup("d", "Finished", "Finished processing. Would you like to return to the start screen?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            reply = msg.exec_()
            if reply == QMessageBox.Yes:
                QApplication.exit(1)

    def fillFileList(self,fileName):
        """ Generates the list of files for the file listbox.
        fileName - currently opened file (marks it in the list).
        Most of the work is to deal with directories in that list.
        It only sees *.wav files. Picks up *.data and *_1.wav files, the first to make the filenames
        red in the list, and the second to know if the files are long."""

        if not os.path.isdir(self.dirName):
            print("ERROR: directory %s doesn't exist" % self.soundFileDir)
            return

        # clear file listbox
        self.listFiles.clearSelection()
        self.listFiles.clearFocus()
        self.listFiles.clear()

        self.listOfFiles = QDir(self.dirName).entryInfoList(['..','*.wav'],filters=QDir.AllDirs|QDir.NoDot|QDir.Files,sort=QDir.DirsFirst)
        listOfDataFiles = QDir(self.dirName).entryList(['*.data'])
        for file in self.listOfFiles:
            # If there is a .data version, colour the name red to show it has been labelled
            item = QListWidgetItem(self.listFiles)
            self.listitemtype = type(item)
            if file.isDir():
                item.setText(file.fileName() + "/")
            else:
                item.setText(file.fileName())
            if file.fileName()+'.data' in listOfDataFiles:
                item.setForeground(Qt.red)
        # mark the current file
        if fileName:
            index = self.listFiles.findItems(fileName+"\/?", Qt.MatchRegExp)
            if len(index)>0:
                self.listFiles.setCurrentItem(index[0])
            else:
                self.listFiles.setCurrentRow(0)

    def listLoadFile(self,current):
        """ Listener for when the user clicks on an item in filelist
        """

        # Need name of file
        if type(current) is self.listitemtype:
            current = current.text()
            current = re.sub('\/.*', '', current)

        self.previousFile = current

        # Update the file list to show the right one
        i=0
        while i<len(self.listOfFiles)-1 and self.listOfFiles[i].fileName() != current:
            i+=1
        if self.listOfFiles[i].isDir() or (i == len(self.listOfFiles)-1 and self.listOfFiles[i].fileName() != current):
            dir = QDir(self.dirName)
            dir.cd(self.listOfFiles[i].fileName())
            # Now repopulate the listbox
            self.dirName=str(dir.absolutePath())
            self.previousFile = None
            if (i == len(self.listOfFiles)-1) and (self.listOfFiles[i].fileName() != current):
                self.loadFile(current)
            self.fillFileList(current)
        return(0)

    def loadFile(self, wipe=True):
        print(self.filename)
        wavobj = wavio.read(self.filename)
        self.sampleRate = wavobj.rate
        self.audiodata = wavobj.data

        # None of the following should be necessary for librosa
        if np.shape(np.shape(self.audiodata))[0] > 1:
            self.audiodata = np.squeeze(self.audiodata[:, 0])
        if self.audiodata.dtype != 'float':
            self.audiodata = self.audiodata.astype('float') #/ 32768.0
            # self.audiodata = self.audiodata[:, 0]
        self.datalength = np.shape(self.audiodata)[0]
        print("Read %d samples, %f s at %d Hz" % (len(self.audiodata), float(self.datalength)/self.sampleRate, self.sampleRate))

        # Create an instance of the Signal Processing class
        if not hasattr(self, 'sp'):
            self.sp = SignalProc.SignalProc()

        # Get the data for the spectrogram
        self.sgRaw = self.sp.spectrogram(self.audiodata, window_width=256, incr=128, window='Hann', mean_normalise=True, onesided=True,multitaper=False, need_even=False)
        maxsg = np.min(self.sgRaw)
        self.sg = np.abs(np.where(self.sgRaw==0,0.0,10.0 * np.log10(self.sgRaw/maxsg)))

        # Read in stored segments (useful when doing multi-species)
        if wipe or not os.path.isfile(self.filename + '.data'):
            self.segments = []
        else:
            file = open(self.filename + '.data', 'r')
            self.segments = json.load(file)
            file.close()
            if len(self.segments) > 0:
                if self.segments[0][0] == -1:
                    del self.segments[0]
            if len(self.segments) > 0:
                for s in self.segments:
                    if 0 < s[2] < 1.1 and 0 < s[3] < 1.1:
                        # *** Potential for major cockups here. First version didn't normalise the segmen     t data for dragged boxes.
                        # The second version did, storing them as values between 0 and 1. It modified the      original versions by assuming that the spectrogram was 128 pixels high (256 width window).
                        # This version does what it should have done in the first place, which is to reco     rd actual frequencies
                        # The .1 is to take care of rounding errors
                        # TODO: Because of this change (23/8/18) I run a backup on the datafiles in the i     nit
                        s[2] = self.convertYtoFreq(s[2])
                        s[3] = self.convertYtoFreq(s[3])
                        self.segmentsToSave = True

                    # convert single-species IDs to [species]
                    if type(s[4]) is not list:
                        s[4] = [s[4]]

                    # wipe segments if running species-specific analysis:
                    if s[4] == [self.species]:
                        self.segments.remove(s)

            print("%d segments loaded from .data file" % len(self.segments))

        # Update the data that is seen by the other classes
        # TODO: keep an eye on this to add other classes as required
        if hasattr(self, 'seg'):
            self.seg.setNewData(self.audiodata,self.sgRaw,self.sampleRate,256,128)
        else:
            self.seg = Segment.Segment(self.audiodata, self.sgRaw, self.sp, self.sampleRate)
        self.sp.setNewData(self.audiodata,self.sampleRate)

    def convertYtoFreq(self,y,sgy=None):
        """ Unit conversion """
        if sgy is None:
            sgy = np.shape(self.sg)[1]
            return y * self.sampleRate//2 / sgy + self.minFreqShow


class AviaNZ_reviewAll(QMainWindow):
    # Main class for reviewing batch processing results
    # Should call HumanClassify1 somehow

    def __init__(self,root=None,configdir='',minSegment=50):
        # Allow the user to browse a folder and push a button to process that folder to find a target species
        # and sets up the window.
        super(AviaNZ_reviewAll, self).__init__()
        self.root = root
        self.dirName=""
        self.configdir = configdir

        # At this point, the main config file should already be ensured to exist.
        self.configfile = os.path.join(configdir, "AviaNZconfig.txt")
        self.ConfigLoader = SupportClasses.ConfigLoader()
        self.config = self.ConfigLoader.config(self.configfile)
        self.saveConfig = True

        # audio things
        self.audioFormat = QAudioFormat()
        self.audioFormat.setCodec("audio/pcm")
        self.audioFormat.setByteOrder(QAudioFormat.LittleEndian)
        self.audioFormat.setSampleType(QAudioFormat.SignedInt)

        # Make the window and associated widgets
        QMainWindow.__init__(self, root)

        self.statusBar().showMessage("Reviewing file Current/Total")

        self.setWindowTitle('AviaNZ - Review Batch Results')
        self.createFrame()
        self.createMenu()
        self.center()

    def createFrame(self):
        # Make the window and set its size
        self.area = DockArea()
        self.setCentralWidget(self.area)
        self.setFixedSize(800, 500)
        self.setWindowIcon(QIcon('img/Avianz.ico'))

        # Make the docks
        self.d_detection = Dock("Review",size=(500,500))
        # self.d_detection.hideTitleBar()
        self.d_files = Dock("File list", size=(270, 500))

        self.area.addDock(self.d_detection, 'right')
        self.area.addDock(self.d_files, 'left')

        self.w_revLabel = QLabel("  Reviewer")
        self.w_reviewer = QLineEdit()
        self.d_detection.addWidget(self.w_revLabel, row=0, col=0)
        self.d_detection.addWidget(self.w_reviewer, row=0, col=1, colspan=2)
        self.w_browse = QPushButton("  &Browse Folder")
        self.w_browse.setToolTip("Can select a folder with sub folders to process")
        self.w_browse.setFixedHeight(50)
        self.w_browse.setStyleSheet('QPushButton {background-color: #A3C1DA; font-weight: bold; font-size:14px}')
        self.w_dir = QPlainTextEdit()
        self.w_dir.setFixedHeight(50)
        self.w_dir.setPlainText('')
        self.w_dir.setToolTip("The folder being processed")
        self.d_detection.addWidget(self.w_dir,row=1,col=1,colspan=2)
        self.d_detection.addWidget(self.w_browse,row=1,col=0)

        self.w_speLabel1 = QLabel("  Select Species")
        self.d_detection.addWidget(self.w_speLabel1,row=2,col=0)
        self.w_spe1 = QComboBox()
        self.spList = ['All species']
        self.w_spe1.addItems(self.spList)
        self.d_detection.addWidget(self.w_spe1,row=2,col=1,colspan=2)

        self.w_resLabel = QLabel("  Time Resolution in Excel Output (s)")
        self.d_detection.addWidget(self.w_resLabel, row=3, col=0)
        self.w_res = QSpinBox()
        self.w_res.setRange(1,600)
        self.w_res.setSingleStep(5)
        self.w_res.setValue(60)
        self.d_detection.addWidget(self.w_res, row=3, col=1, colspan=2)

        # sliders to select min/max frequencies for ALL SPECIES only
        self.fLow = QSlider(Qt.Horizontal)
        self.fLow.setTickPosition(QSlider.TicksBelow)
        self.fLow.setTickInterval(500)
        self.fLow.setRange(0, 5000)
        self.fLow.setSingleStep(100)
        self.fLowtext = QLabel('  Show freq. above (Hz)')
        self.fLowvalue = QLabel('0')
        receiverL = lambda value: self.fLowvalue.setText(str(value))
        self.fLow.valueChanged.connect(receiverL)
        self.fHigh = QSlider(Qt.Horizontal)
        self.fHigh.setTickPosition(QSlider.TicksBelow)
        self.fHigh.setTickInterval(1000)
        self.fHigh.setRange(4000, 32000)
        self.fHigh.setSingleStep(250)
        self.fHightext = QLabel('  Show freq. below (Hz)')
        self.fHighvalue = QLabel('4000')
        receiverH = lambda value: self.fHighvalue.setText(str(value))
        self.fHigh.valueChanged.connect(receiverH)
        # add sliders to dock
        self.d_detection.addWidget(self.fLowtext, row=4, col=0)
        self.d_detection.addWidget(self.fLow, row=4, col=1)
        self.d_detection.addWidget(self.fLowvalue, row=4, col=2)
        self.d_detection.addWidget(self.fHightext, row=5, col=0)
        self.d_detection.addWidget(self.fHigh, row=5, col=1)
        self.d_detection.addWidget(self.fHighvalue, row=5, col=2)

        self.w_processButton = QPushButton("&Review Folder")
        self.w_processButton.clicked.connect(self.review)
        self.d_detection.addWidget(self.w_processButton,row=11,col=2)
        self.w_processButton.setStyleSheet('QPushButton {background-color: #A3C1DA; font-weight: bold; font-size:14px}')

        self.w_browse.clicked.connect(self.browse)
        # print("spList after browse: ", self.spList)

        self.w_files = pg.LayoutWidget()
        self.d_files.addWidget(self.w_files)
        self.w_files.addWidget(QLabel('View Only'), row=0, col=0)
        self.w_files.addWidget(QLabel('use Browse Folder to choose data for processing'), row=1, col=0)
        # self.w_files.addWidget(QLabel(''), row=2, col=0)
        # List to hold the list of files
        self.listFiles = QListWidget()
        self.listFiles.setMinimumWidth(150)
        self.listFiles.itemDoubleClicked.connect(self.listLoadFile)
        self.w_files.addWidget(self.listFiles, row=2, col=0)

        self.show()

    def createMenu(self):
        """ Create the basic menu.
        """

        helpMenu = self.menuBar().addMenu("&Help")
        helpMenu.addAction("Help", self.showHelp,"Ctrl+H")
        aboutMenu = self.menuBar().addMenu("&About")
        aboutMenu.addAction("About", self.showAbout,"Ctrl+A")
        aboutMenu = self.menuBar().addMenu("&Quit")
        aboutMenu.addAction("Quit", self.quitPro,"Ctrl+Q")

    def showAbout(self):
        """ Create the About Message Box. Text is set in SupportClasses.MessagePopup"""
        msg = SupportClasses.MessagePopup("a", "About", ".")
        msg.exec_()
        return

    def showHelp(self):
        """ Show the user manual (a pdf file)"""
        # TODO: manual is not distributed as pdf now
        import webbrowser
        # webbrowser.open_new(r'file://' + os.path.realpath('./Docs/AviaNZManual.pdf'))
        webbrowser.open_new(r'http://avianz.net/docs/AviaNZManual_v1.1.pdf')

    def quitPro(self):
        """ quit program
        """
        QApplication.quit()

    def center(self):
        # geometry of the main window
        qr = self.frameGeometry()
        # center point of screen
        cp = QDesktopWidget().availableGeometry().center()
        # move rectangle's center point to screen's center point
        qr.moveCenter(cp)
        # top left of rectangle becomes top left of window centering it
        self.move(qr.topLeft())

    def cleanStatus(self):
        self.statusBar().showMessage("Processing file Current/Total")

    def browse(self):
        # self.dirName = QtGui.QFileDialog.getExistingDirectory(self,'Choose Folder to Process',"Wav files (*.wav)")
        if self.dirName:
            self.dirName = QtGui.QFileDialog.getExistingDirectory(self,'Choose Folder to Process',str(self.dirName))
        else:
            self.dirName = QtGui.QFileDialog.getExistingDirectory(self,'Choose Folder to Process')
        #print("Dir:", self.dirName)
        self.w_dir.setPlainText(self.dirName)
        self.spList = set()
        # find species names from the annotations
        for root, dirs, files in os.walk(str(self.dirName)):
            for filename in files:
                if filename.endswith('.wav') and filename+'.data' in files:
                    with open(os.path.join(root, filename+'.data')) as f:
                        segments = json.load(f)
                        for seg in segments:
                            # meta segments
                            if seg[0] == -1:
                                continue

                            for birdName in seg[4]:
                                # strip question mark and convert sp>spp format
                                birdName = re.sub(r'\?$', '', birdName)
                                birdName = re.sub(r'(.*)>(.*)', '\\1 (\\2)', birdName)
                                self.spList.add(birdName)
        self.spList = list(self.spList)
        self.spList.insert(0, 'All species')
        self.w_spe1.clear()
        self.w_spe1.addItems(self.spList)
        self.fillFileList(self.dirName)

    def review(self):
        self.species = self.w_spe1.currentText()
        self.reviewer = self.w_reviewer.text()
        print("Reviewer: ", self.reviewer)
        if self.reviewer == '':
            msg = SupportClasses.MessagePopup("w", "Enter Reviewer", "Please enter reviewer name")
            msg.exec_()
            return

        if self.dirName == '':
            msg = SupportClasses.MessagePopup("w", "Select Folder", "Please select a folder to process!")
            msg.exec_()
            return

        # directory found, reviewer provided, so start review
        # 1. find any .wav+.data files
        # 2. delete old results (xlsx)
        # ! WARNING: any Detection...xlsx files will be DELETED,
        # ! ANYWHERE INSIDE the specified dir, recursively
        total = 0
        for root, dirs, files in os.walk(str(self.dirName)):
            for filename in files:
                filename = os.path.join(root, filename)

                if fnmatch.fnmatch(filename, '*DetectionSummary_*.xlsx'):
                    print("Removing excel file %s" % filename)
                    os.remove(filename)

                if filename.endswith('.wav') and os.path.isfile(filename + '.data'):
                    total = total + 1


        # main file review loop
        cnt = 0
        filesuccess = 1
        for root, dirs, files in os.walk(str(self.dirName)):
            for filename in files:
                DOCRecording = re.search('(\d{6})_(\d{6})', filename)
                filename = os.path.join(root, filename)
                self.filename = filename
                filesuccess = 1
                if filename.endswith('.wav') and os.path.isfile(filename + '.data'):
                    print("Opening file %s" % filename)
                    cnt=cnt+1
                    if os.stat(filename).st_size < 100:
                        print("Skipping empty file")
                        continue

                    if DOCRecording:
                        startTime = DOCRecording.group(2)
                        sTime = int(startTime[:2]) * 3600 + int(startTime[2:4]) * 60 + int(startTime[4:6])
                    else:
                        sTime = 0

                    self.statusBar().showMessage("Reviewing file " + str(cnt) + "/" + str(total) + "...")
                    # load segments
                    self.segments = json.load(open(filename + '.data'))
                    # read in operator from first "segment"
                    if len(self.segments)>0 and self.segments[0][0] == -1:
                        self.operator = self.segments[0][2]
                        del self.segments[0]
                    else:
                        self.operator = "None"

                    self.loadFile()
                    if len(self.segments) == 0:
                        # and skip review dialog, but save the name into excel
                        print("No segments found in file %s" % filename)
                    # file has segments, so call the right review dialog:
                    elif self.species == 'All species':
                        filesuccess = self.review_all(sTime)
                    else:
                        filesuccess = self.review_single(sTime)
                        print("File success: ", filesuccess)

                    # Store the output to an Excel file (no matter if review dialog exit was clean)
                    out = SupportClasses.exportSegments(segments=self.segments, startTime=sTime, dirName=self.dirName, filename=self.filename, datalength=self.datalength, sampleRate=self.sampleRate, resolution=self.w_res.value(), operator=self.operator, reviewer=self.reviewer, species=[self.species], batch=True)
                    out.excel()
                    # Save the corrected segment JSON
                    out.saveAnnotation()

                    # break out of both loops if Esc detected
                    # (return value will be 1 for correct close, 0 for Esc)
                    if filesuccess == 0:
                        break

            # after the loop, check if file wasn't Esc-broken
            if filesuccess == 0:
                break

        # loop complete, all files checked
        # save the excel at the end
        self.statusBar().showMessage("Reviewed files " + str(cnt) + "/" + str(total))
        if filesuccess == 1:
            msg = SupportClasses.MessagePopup("d", "Finished", "All files checked. Would you like to return to the start screen?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            reply = msg.exec_()
            if reply == QMessageBox.Yes:
                QApplication.exit(1)
        else:
            msg = SupportClasses.MessagePopup("w", "Review stopped", "Review stopped at file %s of %s.\nWould you like to return to the start screen?" % (cnt, total))
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            reply = msg.exec_()
            if reply == QMessageBox.Yes:
                QApplication.exit(1)

    def review_single(self, sTime):
        """ Initializes all species dialog.
            Updates self.segments as a side effect.
            Returns 1 for clean completion, 0 for Esc press or other dirty exit.
        """
        # self.segments_other = []
        self.segments_sp = []
        for seg in self.segments:
            for birdName in seg[4]:
                if len(birdName)>0 and birdName[-1] == '?':
                    if self.species == birdName[:-1]:
                        self.segments_sp.append(seg)
                        break
                elif self.species == birdName:
                    self.segments_sp.append(seg)
                    break

        segments = copy.deepcopy(self.segments)
        errorInds = []
        # Initialize the dialog for this file
        if len(self.segments_sp) > 0:
            self.humanClassifyDialog2 = Dialogs.HumanClassify2(self.sg, self.audiodata, self.segments_sp,
                                           self.species, self.sampleRate, self.audioFormat,
                                           self.config['incr'], self.lut, self.colourStart,
                                           self.colourEnd, self.config['invertColourMap'],
                                           self.config['brightness'], self.config['contrast'],
                                           filename = self.filename)

            success = self.humanClassifyDialog2.exec_()
            # capture Esc press or other "dirty" exit:
            if success == 0:
                 return(0)
            errorInds = self.humanClassifyDialog2.getValues()
            print("Errors: ", errorInds, len(errorInds))

        outputErrors = []
        if len(errorInds) > 0:
            # print(self.segments)
            for ind in errorInds:
                outputErrors.append(self.segments[ind])
                # self.deleteSegment(id=ids[ind], hr=True)
                # ids = [x - 1 for x in ids]
            self.segmentsToSave = True
            if self.config['saveCorrections']:
                # Save the errors in a file
                file = open(self.filename + '.corrections_' + str(self.species), 'a')
                json.dump(outputErrors, file)
                file.close()

        # Produce segments:
        for seg in outputErrors:
            if seg in self.segments:
                segments.remove(seg)
        # remove '?'
        for seg in segments:
            for sp in seg[4]:
                if sp[:-1] == self.species and sp[-1] == '?':
                    sp = sp[:-1]

        self.segments = segments
        return(1)

    def review_all(self, sTime, minLen=5):
        """ Initializes all species dialog.
            Updates self.segments as a side effect.
            Returns 1 for clean completion, 0 for Esc press or other dirty exit.
        """
        # Load the birdlists:
        # short list is necessary, long list can be None
        self.shortBirdList = self.ConfigLoader.shortbl(self.config['BirdListShort'], self.configdir)
        if self.shortBirdList is None:
            sys.exit()

        # Will be None if fails to load or filename was "None"
        self.longBirdList = self.ConfigLoader.longbl(self.config['BirdListLong'], self.configdir)
        if self.config['BirdListLong'] is None:
            # If don't have a long bird list,
            # check the length of the short bird list is OK, and otherwise split it
            # 40 is a bit random, but 20 in a list is long enough!
            if len(self.shortBirdList) > 40:
                self.longBirdList = self.shortBirdList.copy()
                self.shortBirdList = self.shortBirdList[:40]
            else:
                self.longBirdList = None

        self.humanClassifyDialog1 = Dialogs.HumanClassify1(self.lut,self.colourStart,self.colourEnd,self.config['invertColourMap'], self.config['brightness'], self.config['contrast'], self.shortBirdList, self.longBirdList, self.config['MultipleSpecies'], self)
        self.box1id = -1
        if hasattr(self, 'dialogPos'):
            self.humanClassifyDialog1.resize(self.dialogSize)
            self.humanClassifyDialog1.move(self.dialogPos)
        self.humanClassifyDialog1.setWindowTitle("AviaNZ - reviewing " + self.filename)
        self.humanClassifyNextImage1()
        # connect listeners
        self.humanClassifyDialog1.correct.clicked.connect(self.humanClassifyCorrect1)
        self.humanClassifyDialog1.delete.clicked.connect(self.humanClassifyDelete1)
        self.humanClassifyDialog1.buttonPrev.clicked.connect(self.humanClassifyPrevImage)
        self.humanClassifyDialog1.buttonNext.clicked.connect(self.humanClassifyNextImage1)
        success = self.humanClassifyDialog1.exec_() # 1 on clean exit

        if success == 0:
            self.humanClassifyDialog1.stopPlayback()
            return(0)

        return(1)

    def loadFile(self):
        wavobj = wavio.read(self.filename)
        self.sampleRate = wavobj.rate
        self.audiodata = wavobj.data
        self.audioFormat.setChannelCount(np.shape(self.audiodata)[1])
        self.audioFormat.setSampleRate(self.sampleRate)
        self.audioFormat.setSampleSize(wavobj.sampwidth*8)
        print("Detected format: %d channels, %d Hz, %d bit samples" % (self.audioFormat.channelCount(), self.audioFormat.sampleRate(), self.audioFormat.sampleSize()))

        # None of the following should be necessary for librosa
        if self.audiodata.dtype is not 'float':
            self.audiodata = self.audiodata.astype('float') #/ 32768.0
        if np.shape(np.shape(self.audiodata))[0]>1:
            self.audiodata = self.audiodata[:,0]
        self.datalength = np.shape(self.audiodata)[0]
        print("Length of file is ",len(self.audiodata),float(self.datalength)/self.sampleRate,self.sampleRate)
        # self.w_dir.setPlainText(self.filename)

        if (self.species=='Kiwi' or self.species=='Ruru') and self.sampleRate!=16000:
            self.audiodata = librosa.core.audio.resample(self.audiodata,self.sampleRate,16000)
            self.sampleRate=16000
            self.audioFormat.setSampleRate(self.sampleRate)
            self.datalength = np.shape(self.audiodata)[0]
            print("File was downsampled to %d" % self.sampleRate)

        # Create an instance of the Signal Processing class
        if not hasattr(self,'sp'):
            self.sp = SignalProc.SignalProc()

        # Filter the audiodata based on initial sliders
        minFreq = max(self.fLow.value(), 0)
        maxFreq = min(self.fHigh.value(), self.sampleRate//2)
        if maxFreq - minFreq < 100:
            print("ERROR: less than 100 Hz band set for spectrogram")
            return
        print("Filtering samples to %d - %d Hz" % (minFreq, maxFreq))
        self.audiodata = self.sp.ButterworthBandpass(self.audiodata, self.sampleRate, minFreq, maxFreq)

        # Get the data for the spectrogram
        self.sgRaw = self.sp.spectrogram(self.audiodata, window_width=256, incr=128, window='Hann', mean_normalise=True, onesided=True,multitaper=False, need_even=False)
        maxsg = np.min(self.sgRaw)
        self.sg = np.abs(np.where(self.sgRaw==0,0.0,10.0 * np.log10(self.sgRaw/maxsg)))
        self.setColourMap()

        # trim the spectrogram
        # TODO: could actually skip filtering above
        height = self.sampleRate//2 / np.shape(self.sg)[1]
        pixelstart = int(minFreq/height)
        pixelend = int(maxFreq/height)
        self.sg = self.sg[:,pixelstart:pixelend]

        # Update the data that is seen by the other classes
        # TODO: keep an eye on this to add other classes as required
        # self.seg.setNewData(self.audiodata,self.sgRaw,self.sampleRate,256,128)
        self.sp.setNewData(self.audiodata,self.sampleRate)

    def humanClassifyNextImage1(self):
        # Get the next image
        if self.box1id < len(self.segments)-1:
            self.box1id += 1
            # update "done/to go" numbers:
            self.humanClassifyDialog1.setSegNumbers(self.box1id, len(self.segments))
            # Check if have moved to next segment, and if so load it
            # If there was a section without segments this would be a bit inefficient, actually no, it was wrong!

            # Show the next segment
            #print(self.segments[self.box1id])
            x1nob = self.segments[self.box1id][0]
            x2nob = self.segments[self.box1id][1]
            x1 = int(self.convertAmpltoSpec(x1nob - self.config['reviewSpecBuffer']))
            x1 = max(x1, 0)
            x2 = int(self.convertAmpltoSpec(x2nob + self.config['reviewSpecBuffer']))
            x2 = min(x2, len(self.sg))
            x3 = int((x1nob - self.config['reviewSpecBuffer']) * self.sampleRate)
            x3 = max(x3, 0)
            x4 = int((x2nob + self.config['reviewSpecBuffer']) * self.sampleRate)
            x4 = min(x4, len(self.audiodata))
            # these pass the axis limits set by slider
            minFreq = max(self.fLow.value(), 0)
            maxFreq = min(self.fHigh.value(), self.sampleRate//2)
            self.humanClassifyDialog1.setImage(self.sg[x1:x2, :], self.audiodata[x3:x4], self.sampleRate, self.config['incr'],
                                           self.segments[self.box1id][4], self.convertAmpltoSpec(x1nob)-x1, self.convertAmpltoSpec(x2nob)-x1,
                                           self.segments[self.box1id][0], self.segments[self.box1id][1],
                                           minFreq, maxFreq)

        else:
            msg = SupportClasses.MessagePopup("d", "Finished", "All segments in this file checked")
            msg.exec_()

            # store position to popup the next one in there
            self.dialogSize = self.humanClassifyDialog1.size()
            self.dialogPos = self.humanClassifyDialog1.pos()
            self.humanClassifyDialog1.done(1)

    def humanClassifyPrevImage(self):
        """ Go back one image by changing boxid and calling NextImage.
        Note: won't undo deleted segments."""
        if self.box1id>0:
            self.box1id -= 2
            self.humanClassifyNextImage1()

    def humanClassifyCorrect1(self):
        """ Correct segment labels, save the old ones if necessary """
        self.humanClassifyDialog1.stopPlayback()
        label, self.saveConfig, checkText = self.humanClassifyDialog1.getValues()

        if len(checkText) > 0:
            if label != checkText:
                label = str(checkText)
                self.humanClassifyDialog1.birdTextEntered()
        if len(checkText) > 0:
            if checkText in self.longBirdList:
                pass
            else:
                self.longBirdList.append(checkText)
                self.longBirdList = sorted(self.longBirdList, key=str.lower)
                self.longBirdList.remove('Unidentifiable')
                self.longBirdList.append('Unidentifiable')
                self.ConfigLoader.blwrite(self.longBirdList, self.config['BirdListLong'], self.configdir)

        if label != self.segments[self.box1id][4]:
            if self.config['saveCorrections']:
                # Save the correction
                outputError = [self.segments[self.box1id], label]
                file = open(self.filename + '.corrections', 'a')
                json.dump(outputError, file, indent=1)
                file.close()

            # Update the label on the box if it is in the current page
            self.segments[self.box1id][4] = label

            if self.saveConfig:
                self.longBirdList.append(checkText)
                self.longBirdList = sorted(self.longBirdList, key=str.lower)
                self.longBirdList.remove('Unidentifiable')
                self.longBirdList.append('Unidentifiable')
                self.ConfigLoader.blwrite(self.longBirdList, self.config['BirdListLong'], self.configdir)
        elif '?' in ''.join(label):
            # Remove the question mark, since the user has agreed
            for i in range(len(self.segments[self.box1id][4])):
                if self.segments[self.box1id][4][i][-1] == '?':
                    self.segments[self.box1id][4][i] = self.segments[self.box1id][4][i][:-1]

        self.humanClassifyDialog1.tbox.setText('')
        self.humanClassifyDialog1.tbox.setEnabled(False)
        self.humanClassifyNextImage1()

    def humanClassifyDelete1(self):
        # Delete a segment
        # (no need to update counter then)
        id = self.box1id
        del self.segments[id]

        self.box1id = id-1
        self.segmentsToSave = True
        self.humanClassifyNextImage1()

    def closeDialog(self, ev):
        # (actually a poorly named listener for the Esc key)
        if ev == Qt.Key_Escape and hasattr(self, 'humanClassifyDialog1'):
            self.humanClassifyDialog1.done(0)

    def convertAmpltoSpec(self,x):
        """ Unit conversion """
        return x*self.sampleRate/self.config['incr']

    def setColourMap(self):
        """ Listener for the menu item that chooses a colour map.
        Loads them from the file as appropriate and sets the lookup table.
        """
        cmap = self.config['cmap']

        import colourMaps
        pos, colour, mode = colourMaps.colourMaps(cmap)

        cmap = pg.ColorMap(pos, colour,mode)
        self.lut = cmap.getLookupTable(0.0, 1.0, 256)
        minsg = np.min(self.sg)
        maxsg = np.max(self.sg)
        self.colourStart = (self.config['brightness'] / 100.0 * self.config['contrast'] / 100.0) * (maxsg - minsg) + minsg
        self.colourEnd = (maxsg - minsg) * (1.0 - self.config['contrast'] / 100.0) + self.colourStart


    def fillFileList(self,fileName):
        """ Generates the list of files for the file listbox.
        fileName - currently opened file (marks it in the list).
        Most of the work is to deal with directories in that list.
        It only sees *.wav files. Picks up *.data and *_1.wav files, the first to make the filenames
        red in the list, and the second to know if the files are long."""

        if not os.path.isdir(self.dirName):
            print("ERROR: directory %s doesn't exist" % self.soundFileDir)
            return

        # clear file listbox
        self.listFiles.clearSelection()
        self.listFiles.clearFocus()
        self.listFiles.clear()

        self.listOfFiles = QDir(self.dirName).entryInfoList(['..','*.wav'],filters=QDir.AllDirs|QDir.NoDot|QDir.Files,sort=QDir.DirsFirst)
        listOfDataFiles = QDir(self.dirName).entryList(['*.data'])
        for file in self.listOfFiles:
            # If there is a .data version, colour the name red to show it has been labelled
            item = QListWidgetItem(self.listFiles)
            self.listitemtype = type(item)
            if file.isDir():
                item.setText(file.fileName() + "/")
            else:
                item.setText(file.fileName())
            if file.fileName()+'.data' in listOfDataFiles:
                item.setForeground(Qt.red)

    def listLoadFile(self,current):
        """ Listener for when the user clicks on an item in filelist
        """

        # Need name of file
        if type(current) is self.listitemtype:
            current = current.text()
            current = re.sub('\/.*', '', current)

        self.previousFile = current

        # Update the file list to show the right one
        i=0
        while i<len(self.listOfFiles)-1 and self.listOfFiles[i].fileName() != current:
            i+=1
        if self.listOfFiles[i].isDir() or (i == len(self.listOfFiles)-1 and self.listOfFiles[i].fileName() != current):
            dir = QDir(self.dirName)
            dir.cd(self.listOfFiles[i].fileName())
            # Now repopulate the listbox
            self.dirName=str(dir.absolutePath())
            self.listFiles.clearSelection()
            self.listFiles.clearFocus()
            self.listFiles.clear()
            self.previousFile = None
            if (i == len(self.listOfFiles)-1) and (self.listOfFiles[i].fileName() != current):
                self.loadFile(current)
            self.fillFileList(current)
            # Show the selected file
            index = self.listFiles.findItems(os.path.basename(current), Qt.MatchExactly)
            if len(index) > 0:
                self.listFiles.setCurrentItem(index[0])
        return(0)
