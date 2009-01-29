#
# Makefile for KeepNote
#
# I keep common building task here
#

PKG=keepnote
VERSION=0.5.2

# release filenames
SDIST_FILE=$(PKG)-$(VERSION).tar.gz
RPM_FILE=$(PKG)-$(VERSION)-1.noarch.rpm
EBUILD_FILE=$(PKG)-$(VERSION).ebuild
DEB_FILE=$(PKG)_$(VERSION)-1_all.deb
WININSTALLER_FILE=$(PKG)-$(VERSION).exe

# release file locations
SDIST=dist/$(SDIST_FILE)
RPM=dist/$(RPM_FILE)
DEB=dist/$(DEB_FILE)
EBUILD=dist/$(EBUILD_FILE)
WININSTALLER=dist/$(WININSTALLER_FILE)

# files to upload
UPLOAD_FILES=$(SDIST) $(RPM) $(DEB) $(EBUILD) $(WININSTALLER)

# windows related variables
WINDIR=dist/$(PKG)-$(VERSION).win
WINEXE=$(WINDIR)/$(PKG).exe
WININSTALLER_SRC=installer.iss


# personal www paths
LINUX_WWW=/var/www/dev/rasm/keepnote
WIN_WWW=/z/mnt/big/www/dev/rasm/keepnote


#=============================================================================
# linux build

all: $(UPLOAD_FILES)

# source distribution *.tar.gz
sdist: $(SDIST)
$(SDIST):
	python setup.py sdist

# RPM binary package
rpm: $(RPM)
$(RPM):
	python setup.py bdist --format=rpm

# Debian package
deb: $(DEB)
$(DEB): $(SDIST)
	pkg/deb/make-deb.sh $(VERSION)
	mv pkg/deb/$(DEB_FILE) $(DEB)

# Gentoo package
ebuild: $(EBUILD)
$(EBUILD):
	cp pkg/ebuild/$(PKG)-template.ebuild $(EBUILD)

clean:
	rm -rf $(UPLOAD_FILES) $(WINDIR) 


#=============================================================================
# wine build

winebuild: $(WINEXE)
$(WINEXE):
	./wine.sh python setup.py py2exe
	./wine.sh python setup.py py2exe
	python pkg/win/fix_pe.py


wineinstaller: $(WININSTALLER)
$(WININSTALLER): $(WINEXE) $(WININSTALLER_SRC)
	./wine.sh iscc $(WININSTALLER_SRC)

$(WININSTALLER_SRC):
	python pkg/win/make-win-installer-src.py \
		pkg/win/installer-template.iss > $(WININSTALLER_SRC)

winclean:
	rm -rf $(WININSTALLER) $(WININSTALLER_SRC) $(WINDIR)

#=============================================================================
# linux upload

pypi:
	python setup.py register


upload: $(UPLOAD_FILES)
	cp $(UPLOAD_FILES) $(LINUX_WWW)/download
	tar zxv -C $(LINUX_WWW)/download \
	    -f $(LINUX_WWW)/download/$(SDIST_FILE)



#=============================================================================
# windows build

winbuild:
	python setup.py py2exe
	iscc installer.iss

winupload:
	cp $(WININSTALLER) $(WIN_WWW)/download
