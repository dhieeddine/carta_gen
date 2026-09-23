$file = Get-ChildItem -Path . -Filter "*mis_a_jour.docx" | Select-Object -First 1
$docFile = $file.FullName
$pdfFile = $docFile.Substring(0, $docFile.Length - 5) + ".pdf"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($docFile)
    $pageCount = $doc.ComputeStatistics(2)
    $doc.SaveAs([ref]$pdfFile, [ref]17)
    $doc.Close()
    Write-Host "SUCCESS: PDF created with $pageCount pages at $pdfFile"
}
finally {
    $word.Quit()
}
