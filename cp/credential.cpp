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

HRESULT NeoFaceCredential::GetSubmitButtonValue(DWORD id, DWORD *adjacent) {
    if (id != 1) return E_INVALIDARG;
    *adjacent = 0;
    return S_OK;
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
    if (!WaitNamedPipeW(L"\\\\.\\pipe\\NeoFace", 15000)) return false;
    HANDLE h = CreateFileW(L"\\\\.\\pipe\\NeoFace", GENERIC_READ | GENERIC_WRITE,
        0, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return false;
    char req[256];
    char ubuf[128];
    WideCharToMultiByte(CP_UTF8, 0, user, -1, ubuf, 128, NULL, NULL);
    wsprintfA(req, "VERIFY %s", ubuf);
    char resp[16] = { 0 };
    DWORD wr = 0, rr = 0;
    BOOL ok = TransactNamedPipe(h, req, (DWORD)strlen(req) + 1, resp, 15, &rr, NULL);
    CloseHandle(h);
    return ok && rr >= 2 && resp[0] == 'O' && resp[1] == 'K';
}

HRESULT NeoFaceCredential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE *resp,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION *serial,
    LPWSTR *status, CREDENTIAL_PROVIDER_STATUS_ICON *icon) {
    *icon = CPSI_NONE;
    *status = NULL;
    wchar_t domain[64] = { 0 }, user[128] = { 0 }, pass[256] = { 0 };
    if (!ReadMachineCred(domain, 64, user, 128, pass, 256)) {
        SHStrDupW(L"NeoFace not set up - run set_password_machine (admin) first", status);
        *icon = CPSI_ERROR;
        *resp = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        return S_OK;
    }
    if (!PipeVerify(user)) {
        SHStrDupW(L"Face not recognized - try again or use PIN", status);
        *icon = CPSI_WARNING;
        *resp = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        SecureZeroMemory(pass, sizeof(pass));
        return S_OK;
    }
    ULONG pkg = 0;
    HRESULT hr = NeoGetAuthPackage(&pkg);
    BYTE *rgb = NULL;
    DWORD cb = 0;
    if (SUCCEEDED(hr)) hr = NeoPackUnlockLogon(domain, user, pass, _cpus, &rgb, &cb);
    SecureZeroMemory(pass, sizeof(pass));
    if (FAILED(hr)) {
        SHStrDupW(L"NeoFace logon packaging failed - use PIN", status);
        *icon = CPSI_ERROR;
        *resp = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        return S_OK;
    }
    serial->ulAuthenticationPackage = pkg;
    serial->cbSerialization = cb;
    serial->rgbSerialization = rgb;
    serial->clsidCredentialProvider = CLSID_NeoFace;
    *resp = CPGSR_RETURN_CREDENTIAL_FINISHED;
    return S_OK;
}
