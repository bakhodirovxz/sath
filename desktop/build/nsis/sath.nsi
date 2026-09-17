; Sath installer (NSIS). Foydalanuvchi profiliga o'rnatadi (admin kerak emas).
;   makensis /DVERSION=0.3.0 /DSTAGE=<stage papka> /DOUT=<chiqish exe> /DICON=<sath.ico> sath.nsi
Unicode true
SetCompressor /SOLID lzma
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
!define MUI_FINISHPAGE_RUN_PARAMETERS "--app-template Sath"
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
  ; eski versiya ustiga: portable/ (sozlamalar) saqlanadi, qolgani yangilanadi
  File /r /x "portable" "${STAGE}\*"
  IfFileExists "$INSTDIR\portable\config\userpref.blend" +2 0
    File /r "${STAGE}\portable"
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
  CreateShortcut "$SMPROGRAMS\Sath\Sath.lnk" "$INSTDIR\Sath.exe" "--app-template Sath" "$INSTDIR\Sath.exe" 0
  CreateShortcut "$SMPROGRAMS\Sath\Sath ni o'chirish.lnk" "$INSTDIR\Uninstall-Sath.exe"
  CreateShortcut "$DESKTOP\Sath.lnk" "$INSTDIR\Sath.exe" "--app-template Sath" "$INSTDIR\Sath.exe" 0
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
