#pragma once
#include <windows.h>
#include <ntsecapi.h>
#include <credentialprovider.h>

HRESULT NeoGetAuthPackage(ULONG *pul);
HRESULT NeoPackUnlockLogon(PWSTR domain, PWSTR user, PWSTR pass,
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, BYTE **rgb, DWORD *cb);
