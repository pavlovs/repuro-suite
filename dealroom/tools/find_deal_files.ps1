param(
    [Parameter(Mandatory=$true)]
    [string]$Query,

    [string]$FileType = "*",

    [int]$Limit = 30,

    [switch]$DirsOnly
)

$base = "C:\Users\X1\Documents\OneDrive - Kamu Kapital\Dokumente - Kamu Kapital"
$repuro = "$base\CLAUDE_REPURO"
$targets = "$base\3_Deals\3_Targets"

$searchPaths = @($repuro, $targets)

if ($DirsOnly) {
    foreach ($sp in $searchPaths) {
        if (Test-Path $sp) {
            Get-ChildItem -Path $sp -Recurse -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -imatch $Query } |
                ForEach-Object { $_.FullName }
        }
    }
} else {
    $filter = if ($FileType -eq "*") { "*" } else { "*.$FileType" }
    $results = @()
    foreach ($sp in $searchPaths) {
        if (Test-Path $sp) {
            $results += Get-ChildItem -Path $sp -Recurse -Filter $filter -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -imatch $Query }
        }
    }
    $results |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First $Limit |
        ForEach-Object {
            "{0:yyyy-MM-dd} {1,12} {2}" -f $_.LastWriteTime, $_.Length, $_.FullName
        }
}
