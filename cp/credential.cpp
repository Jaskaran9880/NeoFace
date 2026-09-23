#include "credential.h"
#include "guid.h"
#include "kerb.h"
#include <new>
#include <shlwapi.h>
#pragma comment(lib, "shlwapi.lib")

NeoFaceCredential::NeoFaceCredential() : _cRef(1), _cpus(CPUS_LOGON) { DllAddRef(); }

HRESULT NeoFaceCredential::QueryInterface(REFIID riid, void **ppv) {
    if (!ppv) return E_INVALIDARG;
    *ppv = NULL;
    if (riid == IID_IUnknown || riid == IID_ICredentialProviderCredential) *ppv = (ICredentialProviderCredential*)this;
    else return E_NOINTERFACE;
    AddRef();
    return S_OK;
}

ULONG NeoFaceCredential::AddRef() { return InterlockedIncrement(&_cRef); }
ULONG NeoFaceCredential::Release() {
    LONG c = InterlockedDecrement(&_cRef);
    if (!c) delete this;
    return c;
}

HRESULT NeoFaceCredential::Advise(ICredentialProviderCredentialEvents*) { return S_OK; }
HRESULT NeoFaceCredential::UnAdvise() { return S_OK; }
HRESULT NeoFaceCredential::SetSelected(BOOL *a) { *a = FALSE; return S_OK; }
HRESULT NeoFaceCredential::SetDeselected() { return S_OK; }

HRESULT NeoFaceCredential::GetFieldState(DWORD id, CREDENTIAL_PROVIDER_FIELD_STATE *s, CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE *i) {
    if (id == 0) { *s = CPFS_DISPLAY_IN_BOTH; *i = CPFIS_NONE; return S_OK; }
    if (id == 1) { *s = CPFS_DISPLAY_IN_SELECTED_TILE; *i = CPFIS_NONE; return S_OK; }
    return E_INVALIDARG;
}

HRESULT NeoFaceCredential::GetStringValue(DWORD id, LPWSTR *v) {
    if (id == 0) return SHStrDupW(L"NeoFace - look at camera, then click below", v);
    if (id == 1) return SHStrDupW(L"Unlock with face", v);
    return E_INVALIDARG;
}

HRESULT NeoFaceCredential::GetBitmapValue(DWORD id, HBITMAP *phbmp) {
    if (!phbmp) return E_INVALIDARG;
    *phbmp = NULL;
    if (id != 0) return E_INVALIDARG;
    const WCHAR *path = L"C:\\Program Files\\NeoFace\\icon.bmp";
    *phbmp = (HBITMAP)LoadImageW(NULL, path, IMAGE_BITMAP, 0, 0,
        LR_LOADFROMFILE | LR_CREATEDIBSECTION);
    if (!*phbmp) return E_FAIL;
    return S_OK;
}

HRESULT NeoFaceCredential::GetSubmitButtonValue(DWORD id, DWORD *adjacent) {
    if (id != 1) return E_INVALIDARG;
    *adjacent = 0;
    return S_OK;
}

static void CpLog(const char *msg) {
    HANDLE h = CreateFileW(L"C:\\ProgramData\\NeoFace\\cp.log", GENERIC_WRITE,
        FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    SetFilePointer(h, 0, NULL, FILE_END);
    char buf[256];
    SYSTEMTIME st;
    GetLocalTime(&st);
    wsprintfA(buf, "%02d:%02d:%02d %s\r\n", st.wHour, st.wMinute, st.wSecond, msg);
    DWORD wr = 0;
    WriteFile(h, buf, (DWORD)strlen(buf), &wr, NULL);
    CloseHandle(h);
}

static bool ReadMachineCred(wchar_t *domain, int dcap, wchar_t *user, int ucap, wchar_t *pass, int pcap) {
    HANDLE h = CreateFileW(L"C:\\ProgramData\\NeoFace\\cred.bin", GENERIC_READ,
        FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return false;
    DWORD len = GetFileSize(h, NULL);
    BYTE *blob = (BYTE*)LocalAlloc(0, len);
    DWORD rd = 0;
    BOOL ok = ReadFile(h, blob, len, &rd, NULL);
    CloseHandle(h);
    if (!ok) { LocalFree(blob); return false; }
    DATA_BLOB in = { len, blob }, out = { 0, NULL };
    BOOL dec = CryptUnprotectData(&in, NULL, NULL, NULL, NULL, CRYPTPROTECT_LOCAL_MACHINE, &out);
    LocalFree(blob);
    if (!dec) return false;
    char *txt = (char*)LocalAlloc(0, out.cbData + 1);
    memcpy(txt, out.pbData, out.cbData);
    txt[out.cbData] = 0;
    LocalFree(out.pbData);
    char *d = txt, *u = strchr(txt, '\n'), *p = NULL;
    if (u) { *u++ = 0; p = strchr(u, '\n'); if (p) *p++ = 0; }
    bool good = (u && p);
    if (good) {
        MultiByteToWideChar(CP_UTF8, 0, d, -1, domain, dcap);
        MultiByteToWideChar(CP_UTF8, 0, u, -1, user, ucap);
        MultiByteToWideChar(CP_UTF8, 0, p, -1, pass, pcap);
    }
    SecureZeroMemory(txt, out.cbData + 1);
    LocalFree(txt);
    return good;
}

static bool PipeVerify(const wchar_t *user) {
    char req[256];
    char ubuf[128];
    WideCharToMultiByte(CP_UTF8, 0, user, -1, ubuf, 128, NULL, NULL);
    wsprintfA(req, "VERIFY %s", ubuf);

    HANDLE h = INVALID_HANDLE_VALUE;
    for (int i = 0; i < 5; i++) {
        h = CreateFileW(L"\\\\.\\pipe\\NeoFace", GENERIC_READ | GENERIC_WRITE,
            0, NULL, OPEN_EXISTING, 0, NULL);
        if (h != INVALID_HANDLE_VALUE) break;
        CpLog("pipe retry");
        Sleep(2000);
    }
    if (h == INVALID_HANDLE_VALUE) { CpLog("pipe open FAIL"); return false; }

    DWORD mode = PIPE_READMODE_MESSAGE;
    SetNamedPipeHandleState(h, &mode, NULL, NULL);

    DWORD wr = 0;
    if (!WriteFile(h, req, (DWORD)strlen(req) + 1, &wr, NULL)) {
        CpLog("pipe write FAIL");
        CloseHandle(h);
        return false;
    }
    CpLog("pipe sent VERIFY");

    OVERLAPPED ov = { 0 };
    ov.hEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
    char resp[16] = { 0 };
    DWORD rr = 0;
    BOOL reading = ReadFile(h, resp, 15, &rr, &ov);
    if (!reading) {
        DWORD err = GetLastError();
        if (err == ERROR_IO_PENDING) {
            DWORD w = WaitForSingleObject(ov.hEvent, 30000);
            if (w == WAIT_OBJECT_0) {
                GetOverlappedResult(h, &ov, &rr, FALSE);
                reading = TRUE;
            } else {
                CancelIo(h);
                CpLog("pipe read TIMEOUT");
            }
        } else {
            CpLog("pipe read ERR");
        }
    }
    CloseHandle(ov.hEvent);
    CloseHandle(h);

    char dbg[64];
    wsprintfA(dbg, "pipe read %s rr=%d r0=%d r1=%d", reading ? "OK" : "FAIL", rr, resp[0], resp[1]);
    CpLog(dbg);
    return reading && rr >= 2 && resp[0] == 'O' && resp[1] == 'K';
}

HRESULT NeoFaceCredential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE *resp,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION *serial,
    LPWSTR *status, CREDENTIAL_PROVIDER_STATUS_ICON *icon) {
    *icon = CPSI_NONE;
    *status = NULL;
    CpLog("GetSerialization enter");
    wchar_t domain[64] = { 0 }, user[128] = { 0 }, pass[256] = { 0 };
    if (!ReadMachineCred(domain, 64, user, 128, pass, 256)) {
        CpLog("cred read FAIL");
        SHStrDupW(L"NeoFace not set up - run set_password_machine (admin) first", status);
        *icon = CPSI_ERROR;
        *resp = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        return S_OK;
    }
    CpLog("cred read OK");
    if (!PipeVerify(user)) {
        CpLog("pipe verify FAIL");
        SHStrDupW(L"Face not recognized - try again or use PIN", status);
        *icon = CPSI_WARNING;
        *resp = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        SecureZeroMemory(pass, sizeof(pass));
        return S_OK;
    }
    CpLog("pipe verify OK");
    ULONG pkg = 0;
    HRESULT hr = NeoGetAuthPackage(&pkg);
    BYTE *rgb = NULL;
    DWORD cb = 0;
    if (SUCCEEDED(hr)) hr = NeoPackUnlockLogon(domain, user, pass, _cpus, &rgb, &cb);
    SecureZeroMemory(pass, sizeof(pass));
    if (FAILED(hr)) {
        CpLog("kerb pack FAIL");
        SHStrDupW(L"NeoFace logon packaging failed - use PIN", status);
        *icon = CPSI_ERROR;
        *resp = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        return S_OK;
    }
    CpLog("returning credential");
    serial->ulAuthenticationPackage = pkg;
    serial->cbSerialization = cb;
    serial->rgbSerialization = rgb;
    serial->clsidCredentialProvider = CLSID_NeoFace;
    *resp = CPGSR_RETURN_CREDENTIAL_FINISHED;
    return S_OK;
}
