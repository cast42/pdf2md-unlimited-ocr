#!/usr/bin/env fish

set -l script_dir (path dirname (status --current-filename))
set -l project_dir (path resolve "$script_dir/..")
set -l data_dir "$project_dir/data"
set -l destination "$data_dir/14159.pdf"
set -l partial "$destination.part"
set -l url "https://publicaties.vlaanderen.be/view-file/14159"

mkdir -p "$data_dir"

if test -s "$destination"
    echo "Test PDF already exists at $destination"
    exit 0
end

rm -f "$partial"
echo "Downloading $url"

if not curl --fail --location --retry 3 --output "$partial" "$url"
    rm -f "$partial"
    echo "Could not download the test PDF" >&2
    exit 1
end

set -l signature (head -c 5 "$partial")
if test "$signature" != "%PDF-"
    rm -f "$partial"
    echo "The downloaded file is not a PDF" >&2
    exit 1
end

mv "$partial" "$destination"
echo "Saved test PDF to $destination"
