#!/usr/bin/env fish

set -l script_dir (path dirname (status --current-filename))
set -l project_dir (path resolve "$script_dir/..")
set -l data_dir "$project_dir/data"
set -l regression_pdf "$data_dir/14159.pdf"
set -l regression_url "https://publicaties.vlaanderen.be/view-file/14159"
set -l layout_source "$data_dir/verkeersveiligheidsplan-2026-2030.pdf"
set -l layout_url "https://assets.vlaanderen.be/image/upload/v1773667928/repositories-prd/Verkeersveiligheidsplan_Vlaanderen_2026-2030_finaal_g1bm4r.pdf"
set -l layout_sample "$data_dir/vvp-layout-sample.pdf"

mkdir -p "$data_dir"

function download_pdf --argument-names url destination
    if test -s "$destination"
        echo "Test PDF already exists at $destination"
        return 0
    end

    set -l partial "$destination.part"
    rm -f "$partial"
    echo "Downloading $url"

    if not curl --fail --location --retry 3 --output "$partial" "$url"
        rm -f "$partial"
        echo "Could not download the test PDF from $url" >&2
        return 1
    end

    set -l signature (head -c 5 "$partial")
    if test "$signature" != "%PDF-"
        rm -f "$partial"
        echo "The downloaded file from $url is not a PDF" >&2
        return 1
    end

    mv "$partial" "$destination"
    echo "Saved test PDF to $destination"
end

download_pdf "$regression_url" "$regression_pdf"; or exit 1
download_pdf "$layout_url" "$layout_source"; or exit 1

if test -s "$layout_sample"
    echo "Layout sample already exists at $layout_sample"
    exit 0
end

set -l sample_partial "$layout_sample.part"
rm -f "$sample_partial"
echo "Extracting pages 1, 21, 29, and 59 to $layout_sample"

if not uv run pypdfium2 arrange "$layout_source" --pages 1,21,29,59 --output "$sample_partial"
    rm -f "$sample_partial"
    echo "Could not extract the layout sample pages" >&2
    exit 1
end

set -l sample_signature (head -c 5 "$sample_partial")
if test "$sample_signature" != "%PDF-"
    rm -f "$sample_partial"
    echo "The extracted layout sample is not a PDF" >&2
    exit 1
end

mv "$sample_partial" "$layout_sample"
echo "Saved layout sample to $layout_sample"
