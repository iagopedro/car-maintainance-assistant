$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = Split-Path $PSScriptRoot -Parent
$bitmap = New-Object System.Drawing.Bitmap 960, 620
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([System.Drawing.Color]::Transparent)
$gridPen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#e1e6e3')), 1
foreach ($position in 80..880 | Where-Object { $_ % 80 -eq 0 }) {
    $graphics.DrawLine($gridPen, $position, 60, $position, 560)
}
foreach ($position in 60..560 | Where-Object { $_ % 80 -eq 60 }) {
    $graphics.DrawLine($gridPen, 80, $position, 880, $position)
}
$route = New-Object System.Drawing.Drawing2D.GraphicsPath
$route.AddBezier(180, 530, 40, 260, 780, 470, 740, 260)
$route.AddBezier(740, 260, 720, 95, 480, 160, 430, 80)
$edgePen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#dce6df')), 108
$roadPen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#2e5143')), 88
$lanePen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#eef3ed')), 3
$lanePen.DashPattern = @(8, 8)
$graphics.DrawPath($edgePen, $route)
$graphics.DrawPath($roadPen, $route)
$graphics.DrawPath($lanePen, $route)
$carBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#e9a16d'))
$glassBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#254538'))
$graphics.FillRectangle($carBrush, 440, 353, 48, 25)
$graphics.FillRectangle($glassBrush, 452, 356, 19, 19)
$markerPen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#c3532a')), 5
$graphics.DrawLine($markerPen, 406, 105, 406, 32)
$graphics.FillRectangle($carBrush, 406, 32, 42, 26)
$bitmap.Save((Join-Path $root 'static/road.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
$icon = New-Object System.Drawing.Bitmap 64, 64
$graphics = [System.Drawing.Graphics]::FromImage($icon)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#146c50'))
$iconPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), 5
$graphics.DrawBezier($iconPen, 16, 49, 52, 48, 10, 15, 48, 15)
$graphics.FillRectangle([System.Drawing.Brushes]::White, 11, 44, 10, 10)
$graphics.FillRectangle([System.Drawing.Brushes]::White, 43, 10, 10, 10)
$icon.Save((Join-Path $root 'static/favicon.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$icon.Dispose()
foreach ($resource in @($gridPen, $route, $edgePen, $roadPen, $lanePen, $carBrush, $glassBrush, $markerPen, $iconPen)) { $resource.Dispose() }
Write-Output 'Generated road.png and favicon.png.'