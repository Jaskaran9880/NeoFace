#include "kerb.h"
#pragma comment(lib, "secur32.lib")

HRESULT NeoGetAuthPackage(ULONG *pul) {
    HANDLE hLsa = NULL;
    NTSTATUS st = LsaConnectUntrusted(&hLsa);
    if (st != 0) return HRESULT_FROM_WIN32(LsaNtStatusToWinError(st));
    LSA_STRING name;
    char buf[] = "Negotiate";
    name.Buffer = buf;
    name.Length = (USHORT)strlen(buf);
    name.MaximumLength = name.Length + 1;
    ULONG pkg = 0;
    st = LsaLookupAuthenticationPackage(hLsa, &name, &pkg);
    LsaDeregisterLogonProcess(hLsa);
    if (st != 0) return HRESULT_FROM_WIN32(LsaNtStatusToWinError(st));
    *pul = pkg;
    return S_OK;
}

static HRESULT DupString(PWSTR src, USHORT *len, USHORT *maxLen, PWSTR *out) {
    size_t chars = wcslen(src);
    size_t bytes = (chars + 1) * sizeof(WCHAR);
    PWSTR d = (PWSTR)CoTaskMemAlloc(bytes);
    if (!d) return E_OUTOFMEMORY;
    memcpy(d, src, bytes);
    *out = d;
    *len = (USHORT)(chars * sizeof(WCHAR));
    *maxLen = (USHORT)bytes;
    return S_OK;
}

HRESULT NeoPackUnlockLogon(PWSTR domain, PWSTR user, PWSTR pass,
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, BYTE **rgb, DWORD *cb) {
    if (!domain || !user || !pass || !rgb || !cb) return E_INVALIDARG;
    *rgb = NULL;
    *cb = 0;

    KERB_INTERACTIVE_UNLOCK_LOGON kiul;
    ZeroMemory(&kiul, sizeof(kiul));
    kiul.Logon.MessageType = (cpus == CPUS_UNLOCK_WORKSTATION)
        ? KerbWorkstationUnlockLogon : KerbInteractiveLogon;

    HRESULT hr = DupString(domain, &kiul.Logon.LogonDomainName.Length,
        &kiul.Logon.LogonDomainName.MaximumLength, &kiul.Logon.LogonDomainName.Buffer);
    if (FAILED(hr)) return hr;
    hr = DupString(user, &kiul.Logon.UserName.Length,
        &kiul.Logon.UserName.MaximumLength, &kiul.Logon.UserName.Buffer);
    if (FAILED(hr)) { CoTaskMemFree(kiul.Logon.LogonDomainName.Buffer); return hr; }
    hr = DupString(pass, &kiul.Logon.Password.Length,
        &kiul.Logon.Password.MaximumLength, &kiul.Logon.Password.Buffer);
    if (FAILED(hr)) {
        CoTaskMemFree(kiul.Logon.LogonDomainName.Buffer);
        CoTaskMemFree(kiul.Logon.UserName.Buffer);
        return hr;
    }

    {
        DWORD size = sizeof(KERB_INTERACTIVE_UNLOCK_LOGON)
            + kiul.Logon.LogonDomainName.MaximumLength
            + kiul.Logon.UserName.MaximumLength
            + kiul.Logon.Password.MaximumLength;
        BYTE *buf = (BYTE*)CoTaskMemAlloc(size);
        if (!buf) { hr = E_OUTOFMEMORY; goto done; }
        BYTE *p = buf + sizeof(KERB_INTERACTIVE_UNLOCK_LOGON);
        KERB_INTERACTIVE_UNLOCK_LOGON *out = (KERB_INTERACTIVE_UNLOCK_LOGON*)buf;
        out->Logon.MessageType = kiul.Logon.MessageType;

        out->Logon.LogonDomainName.Length = kiul.Logon.LogonDomainName.Length;
        out->Logon.LogonDomainName.MaximumLength = kiul.Logon.LogonDomainName.MaximumLength;
        out->Logon.LogonDomainName.Buffer = (PWSTR)(p - buf);
        memcpy(p, kiul.Logon.LogonDomainName.Buffer, kiul.Logon.LogonDomainName.MaximumLength);
        p += kiul.Logon.LogonDomainName.MaximumLength;

        out->Logon.UserName.Length = kiul.Logon.UserName.Length;
        out->Logon.UserName.MaximumLength = kiul.Logon.UserName.MaximumLength;
        out->Logon.UserName.Buffer = (PWSTR)(p - buf);
        memcpy(p, kiul.Logon.UserName.Buffer, kiul.Logon.UserName.MaximumLength);
        p += kiul.Logon.UserName.MaximumLength;

        out->Logon.Password.Length = kiul.Logon.Password.Length;
        out->Logon.Password.MaximumLength = kiul.Logon.Password.MaximumLength;
        out->Logon.Password.Buffer = (PWSTR)(p - buf);
        memcpy(p, kiul.Logon.Password.Buffer, kiul.Logon.Password.MaximumLength);

        *rgb = buf;
        *cb = size;
        hr = S_OK;
    }

done:
    SecureZeroMemory(kiul.Logon.Password.Buffer, kiul.Logon.Password.MaximumLength);
    CoTaskMemFree(kiul.Logon.LogonDomainName.Buffer);
    CoTaskMemFree(kiul.Logon.UserName.Buffer);
    CoTaskMemFree(kiul.Logon.Password.Buffer);
    return hr;
}
