TOP    ?= $(shell pwd)
SRC    := $(TOP)
OUTPUT := $(TOP)/build

PHONY += all
all: package

PHONY += package
package:
	mkdir -p "$(OUTPUT)"
	for subdir in bin trendcar extra; do         \
		rm -rf "$(OUTPUT)/$${subdir}";           \
		cp -af "$(SRC)/$${subdir}" "$(OUTPUT)/"; \
		find "$(OUTPUT)/$${subdir}" \( -name "*.pyc" -or -name "*.orig" -or -name "*.new" -or -name "*.bak" -or -name "*.test" -or -name ".*.sw?" -or -name ".DS_Store" \) -exec rm -f {} \; ; \
	done
	cp -af "$(SRC)/LICENSE" "$(OUTPUT)/"; \
	cp -f "$(SRC)/script/setup.sh" "$(OUTPUT)/"
	sed -i '' -e 's/^\([[:space:]]*release_date[[:space:]]*=[[:space:]]*\).*$$/\1$(shell date "+%b %d, %Y")/' "$(OUTPUT)/trendcar/config.ini"
	cd "$(OUTPUT)"; 7za a -mhc=on -mhe=on -p'TrendCar!' "$(OUTPUT)/trendcar.$(shell date "+%Y%m%d").7z" setup.sh bin trendcar extra LICENSE

.PHONY: $(PHONY)
