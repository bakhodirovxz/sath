; Sath installer (NSIS). Foydalanuvchi profiliga o'rnatadi (admin kerak emas).
;   makensis /DVERSION=0.3.0 /DSTAGE=<stage papka> /DOUT=<chiqish exe> /DICON=<sath.ico> sath.nsi
Unicode true
SetCompressor lzma  ; /SOLID emas: 2 GB stage da makensis mmap xatosi beradi
SetCompressorDictSize 64
RequestExecutionLevel user

!include "MUI2.nsh"

Name "Sath ${VERSION}"
OutFile "${OUT}"
InstallDir "$LOCALAPPDATA\Programs\Sath"
InstallDirRegKey HKCU "Software\Sath" "InstallDir"
BrandingText "Sath ${VERSION} — gidroelektrostansiya BIM"

!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\Sath.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Sath ni ishga tushirish"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Russian"

Section "Sath" SEC_MAIN
  SetOutPath "$INSTDIR"
  ; eski versiya ustiga: faqat portable\config (foydalanuvchi sozlamalari) saqlanadi, qolgani yangilanadi
  ; 0.3.x dan: FreeCAD olib tashlangan (P4) — eski papka o'chiriladi
  IfFileExists "$INSTDIR\Sath.exe" 0 +2  ; faqat Sath o'rnatilgan papkada (boshqa dasturning freecad\ ini o'chirmaslik uchun)
    RMDir /r "$INSTDIR\freecad"
  File /r /x "portable" "${STAGE}\*"
  ; extension lar va boot skripti HAR DOIM almashadi (olib tashlangan modullar qolib ketmasin)
  RMDir /r "$INSTDIR\portable\extensions\user_default\sath"
  RMDir /r "$INSTDIR\portable\extensions\user_default\bonsai"
  ; Bonsai kodi va bog'liqliklari .local da: eskisi o'chiriladi, stage dagi to'liq .local pastda nusxalanadi
  ; (qayta qurish yo'q; .cache mos kelmasa Blender faqat ~0.1 s qayta skanerlaydi, uchinchi tomon wheels qayta sinxronlanadi)
  RMDir /r "$INSTDIR\portable\extensions\.local"
  RMDir /r "$INSTDIR\portable\extensions\.cache"
  ; portable\scripts foydalanuvchiniki (presetlar, addonlar, app template): faqat Sath fayllari almashadi
  Delete "$INSTDIR\portable\scripts\startup\sath_boot.py"
  Delete "$INSTDIR\portable\scripts\startup\__pycache__\sath_boot.*.pyc"
  SetOutPath "$INSTDIR\portable\extensions"
  File /r "${STAGE}\portable\extensions\*"
  SetOutPath "$INSTDIR\portable\scripts"
  File /r "${STAGE}\portable\scripts\*"
  ; portable\config HECH QACHON o'chirilmaydi; yangi o'rnatishda boshlang'ich userpref.blend qo'yiladi
  IfFileExists "$INSTDIR\portable\config\userpref.blend" +3 0
    SetOutPath "$INSTDIR\portable\config"
    File /r "${STAGE}\portable\config\*"
  SetOutPath "$INSTDIR"
  WriteRegStr HKCU "Software\Sath" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Sath" "Version" "${VERSION}"
  WriteUninstaller "$INSTDIR\Uninstall-Sath.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sath" "DisplayName" "Sath ${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sath" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sath" "Publisher" "Sath jamoasi"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sath" "DisplayIcon" "$INSTDIR\Sath.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sath" "UninstallString" '"$INSTDIR\Uninstall-Sath.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sath" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sath" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\Sath"
  CreateShortcut "$SMPROGRAMS\Sath\Sath.lnk" "$INSTDIR\Sath.exe" "" "$INSTDIR\Sath.exe" 0
  CreateShortcut "$SMPROGRAMS\Sath\Sath ni o'chirish.lnk" "$INSTDIR\Uninstall-Sath.exe"
  CreateShortcut "$DESKTOP\Sath.lnk" "$INSTDIR\Sath.exe" "" "$INSTDIR\Sath.exe" 0
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\Sath\Sath.lnk"
  Delete "$SMPROGRAMS\Sath\Sath ni o'chirish.lnk"
  RMDir "$SMPROGRAMS\Sath"
  Delete "$DESKTOP\Sath.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Sath"
  DeleteRegKey HKCU "Software\Sath"
SectionEnd
