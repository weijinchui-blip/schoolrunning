#!/system/bin/sh
# =====================================================
# 悲伤压缩包 - 合并工具脚本 v.01.90
# 用法: sh tools.sh <command> [args...]
# =====================================================

MODDIR=${0%/*}

# =====================================================
# 公共函数
# =====================================================
remove_path() {
    [ -n "$1" ] && rm -rf "$1" 2>/dev/null
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "❌ 需要 Root 权限"
        exit 1
    fi
}

find_resetprop() {
    for rp in /system/bin/resetprop /system_ext/bin/resetprop /product/bin/resetprop /data/adb/magisk/resetprop /data/adb/ksu/bin/resetprop /data/adb/ap/bin/resetprop; do
        if [ -x "$rp" ]; then
            echo "$rp"
            return 0
        fi
    done
    return 1
}

# =====================================================
# 功能: keybox - 更新keybox文件
# 用法: keybox [github|local]  (无参数时自动: github -> 内置)
# 说明: GitHub 渠道完整流程已内联合并（原 GitHub在线更新Keybox.sh）
# =====================================================
cmd_keybox() {
    CHANNEL="${1:-auto}"
    TRICKY_DIR="/data/adb/tricky_store"
    TARGET_FILE="$TRICKY_DIR/keybox.xml"
    BACKUP_FILE="$TRICKY_DIR/keybox.xml.bak"
    REMOTE_FILE="$TRICKY_DIR/keybox_remote"
    DECODE_FILE="$TRICKY_DIR/keybox_decode"

    GITHUB_URL="https://raw.githubusercontent.com/Yurii0307/yurikey/main/key"

    LOCAL_KEYBOX='<?xml version="1.0"?>
<AndroidAttestation>
    <NumberOfKeyboxes>1</NumberOfKeyboxes>
    <Keybox DeviceID="ASUS-56aa7acc-393b-4ceb-ac68-62da28c458d3">
        <Key algorithm="ecdsa">
            <PrivateKey format="pem">
-----BEGIN EC PRIVATE KEY-----
MHcCAQEEICsWCkcC+pTl58p6qhgG60grTabLZW+7L6BKbhkMqy0poAoGCCqGSM49
AwEHoUQDQgAEecRc8heT7+ottGth8xheYv3I5mbeDxZUyrFSRjBe2ALiO7mq8xbV
Sy14X3+Wqxle4AScKbxIoEJ6zLT+Efylpw==
-----END EC PRIVATE KEY-----
            </PrivateKey>
            <CertificateChain>
                <NumberOfCertificates>3</NumberOfCertificates>
                <Certificate format="pem">
-----BEGIN CERTIFICATE-----
MIICJTCCAaugAwIBAgIKAWmEIJYGc2ZhkTAKBggqhkjOPQQDAjApMRkwFwYDVQQF
ExBmNzc4NzllZTI0ODAwYTY2MQwwCgYDVQQMDANURUUwHhcNMTgxMjAzMjIxNjMw
WhcNMjgxMTMwMjIxNjMwWjApMRkwFwYDVQQFExBhOTRmYjRkM2JmMjE2ZDI2MQww
CgYDVQQMDANURUUwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAR5xFzyF5Pv6i20
a2HzGF5i/cjmZt4PFlTKsVJGMF7YAuI7uarzFtVLLXhff5arGV7gBJwpvEigQnrM
tP4R/KWno4G6MIG3MB0GA1UdDgQWBBTmi+lXlmiYvngSntHQbSJb6SagGDAfBgNV
HSMEGDAWgBS1X8IM09E+6VlpQxRYUMvqlB3iyTAPBgNVHRMBAf8EBTADAQH/MA4G
A1UdDwEB/wQEAwICBDBUBgNVHR8ETTBLMEmgR6BFhkNodHRwczovL2FuZHJvaWQu
Z29vZ2xlYXBpcy5jb20vYXR0ZXN0YXRpb24vY3JsLzAxNjk4NDIwOTYwNjczNjY2
MTkxMAoGCCqGSM49BAMCA2gAMGUCMCZANvh6AXZeU7zqvo0oiukYTudYOLQR79Ml
q4R9hNfN1Np2UpPaGmNmPA9yHbYcXAIxAJJcetx/m5iIG6UbkSZMUBvJkkHHC+6o
ks1f4olSwU964eP+J87Am4+jJjHp0u+p/Q==
-----END CERTIFICATE-----
                </Certificate>
                <Certificate format="pem">
-----BEGIN CERTIFICATE-----
MIID0TCCAbmgAwIBAgIKA4gmZ2BliZaFzDANBgkqhkiG9w0BAQsFADAbMRkwFwYD
VQQFExBmOTIwMDllODUzYjZiMDQ1MB4XDTE4MTIwMzIyMDM0MloXDTI4MTEzMDIy
MDM0MlowKTEZMBcGA1UEBRMQZjc3ODc5ZWUyNDgwMGE2NjEMMAoGA1UEDAwDVEVF
MHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEKuZTvF9FiLxXasiE1WaH4zOrrpS9HStr
wwEsnKed7T3w4MZmS+SUb2OduaHAJqDlaItjLectShx8nSn7MLqFJ50IsQNe0Rji
j5pPar+VQQExmzyjV1Ihn3WB7XrDFYFzo4G2MIGzMB0GA1UdDgQWBBS1X8IM09E+
6VlpQxRYUMvqlB3iyTAfBgNVHSMEGDAWgBQ2YeEAfIgFCVGLRGxH/xpMyepPEjAP
BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwICBDBQBgNVHR8ESTBHMEWgQ6BB
hj9odHRwczovL2FuZHJvaWQuZ29vZ2xlYXBpcy5jb20vYXR0ZXN0YXRpb24vY3Js
L0U4RkExOTYzMTREMkZBMTgwDQYJKoZIhvcNAQELBQADggIBAIC+gN1zMZjGX8iB
EXbZEm0t/gZCWa4fxHOHxo8F18XNXwvn7E4qwTPWJ8hmkWdfqj1bzu6KVr7lqE9g
Scng5zGf+SYD8DwNvJx9bkGSjELwIUeVwDb9PGjyAUIpXKMJqVwR7/eDlJrtHwOU
/jVBAfeYpKqYvDJ3o+PCkfcfgz9CGLhtYStYL2L/bdBePXHnKSIcYbXuaXxfQyLx
0DyDMqUiHpXPGALYXJJyYymgW1QL8ZByDOvnPF8nZZudzlxeCA6/l4Cd5lk9kRv9
QiAQfNNrJvMQK+WkzbdLtvdCLzUU2WGolB4niL8Xq3Rl3ywQ3knKeZPAIqhjJhVY
VS0oxhbmZCvu4Vli4Zv6NZ5LWViMPrLGuHTKxD4j4RhByUn657DgbWETHZYn9K2A
NDgDgJ9+NHFVec0kSbQa3aOQ0QfiZL4CL9x/DESri5HvrUMpsaheGlLs8eZNiKQG
uyuTne1t+rupI3c30agj+LFBMgh3ZQnP8+gj28J0/I81zMk/bLnoppB5ABZq6gzV
lOIujx0Vo0e/ekVBUgDhWWzHy80hM0KoC6/heAeGXlx2IRTJzhONT2qd8UvNlK1A
7liYe5jVAJut76diHHPifydpeX74m6xFaFmBHRVclY7xdvhfj7XrM7HoYzvd65fA
sJIZmSIvI4a2QY3We6X4LCDeDr/Q
-----END CERTIFICATE-----
                </Certificate>
                <Certificate format="pem">
-----BEGIN CERTIFICATE-----
MIIFHDCCAwSgAwIBAgIJANUP8luj8tazMA0GCSqGSIb3DQEBCwUAMBsxGTAXBgNV
BAUTEGY5MjAwOWU4NTNiNmIwNDUwHhcNMTkxMTIyMjAzNzU4WhcNMzQxMTE4MjAz
NzU4WjAbMRkwFwYDVQQFExBmOTIwMDllODUzYjZiMDQ1MIICIjANBgkqhkiG9w0B
AQEFAAOCAg8AMIICCgKCAgEAr7bHgiuxpwHsK7Qui8xUFmOr75gvMsd/dTEDDJdS
Sxtf6An7xyqpRR90PL2abxM1dEqlXnf2tqw1Ne4Xwl5jlRfdnJLmN0pTy/4lj4/7
tv0Sk3iiKkypnEUtR6WfMgH0QZfKHM1+di+y9TFRtv6y//0rb+T+W8a9nsNL/ggj
nar86461qO0rOs2cXjp3kOG1FEJ5MVmFmBGtnrKpa73XpXyTqRxB/M0n1n/W9nGq
C4FSYa04T6N5RIZGBN2z2MT5IKGbFlbC8UrW0DxW7AYImQQcHtGl/m00QLVWutHQ
oVJYnFPlXTcHYvASLu+RhhsbDmxMgJJ0mcDpvsC4PjvB+TxywElgS70vE0XmLD+O
JtvsBslHZvPBKCOdT0MS+tgSOIfga+z1Z1g7+DVagf7quvmag8jfPioyKvxnK/Eg
sTUVi2ghzq8wm27ud/mIM7AY2qEORR8Go3TVB4HzWQgpZrt3i5MIlCaY504LzSRi
igHCzAPlHws+W0rB5N+er5/2pJKnfBSDiCiFAVtCLOZ7gLiMm0jhO2B6tUXHI/+M
RPjy02i59lINMRRev56GKtcd9qO/0kUJWdZTdA2XoS82ixPvZtXQpUpuL12ab+9E
aDK8Z4RHJYYfCT3Q5vNAXaiWQ+8PTWm2QgBR/bkwSWc+NpUFgNPN9PvQi8WEg5Um
AGMCAwEAAaNjMGEwHQYDVR0OBBYEFDZh4QB8iAUJUYtEbEf/GkzJ6k8SMB8GA1Ud
IwQYMBaAFDZh4QB8iAUJUYtEbEf/GkzJ6k8SMA8GA1UdEwEB/wQFMAMBAf8wDgYD
VR0PAQH/BAQDAgIEMA0GCSqGSIb3DQEBCwUAA4ICAQBOMaBc8oumXb2voc7XCWnu
XKhBBK3e2KMGz39t7lA3XXRe2ZLLAkLM5y3J7tURkf5a1SutfdOyXAmeE6SRo83U
h6WszodmMkxK5GM4JGrnt4pBisu5igXEydaW7qq2CdC6DOGjG+mEkN8/TA6p3cno
L/sPyz6evdjLlSeJ8rFBH6xWyIZCbrcpYEJzXaUOEaxxXxgYz5/cTiVKN2M1G2ok
QBUIYSY6bjEL4aUN5cfo7ogP3UvliEo3Eo0YgwuzR2v0KR6C1cZqZJSTnghIC/vA
D32KdNQ+c3N+vl2OTsUVMC1GiWkngNx1OO1+kXW+YTnnTUOtOIswUP/Vqd5SYgAI
mMAfY8U9/iIgkQj6T2W6FsScy94IN9fFhE1UtzmLoBIuUFsVXJMTz+Jucth+IqoW
Fua9v1R93/k98p41pjtFX+H8DslVgfP097vju4KDlqN64xV1grw3ZLl4CiOe/A91
oeLm2UHOq6wn3esB4r2EIQKb6jTVGu5sYCcdWpXr0AUVqcABPdgL+H7qJguBw09o
jm6xNIrw2OocrDKsudk/okr/AwqEyPKw9WnMlQgLIKw1rODG2NvU9oR3GVGdMkUB
ZutL8VuFkERQGt6vQ2OCw0sV47VMkuYbacK/xyZFiRcrPJPb41zgbQj9XAEyLKCH
ex0SdDrx+tWUDqG8At2JHA==
-----END CERTIFICATE-----
                </Certificate>
            </CertificateChain>
        </Key>
        <Key algorithm="rsa">
            <PrivateKey format="pem">
-----BEGIN RSA PRIVATE KEY-----
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
-----END RSA PRIVATE KEY-----
            </PrivateKey>
            <CertificateChain>
                <NumberOfCertificates>3</NumberOfCertificates>
                <Certificate format="pem">
-----BEGIN CERTIFICATE-----
MIIFETCCAvmgAwIBAgIKFVEHQIhjZJWHUzANBgkqhkiG9w0BAQsFADApMRkwFwYD
VQQFExBmNzc4NzllZTI0ODAwYTY2MQwwCgYDVQQMDANURUUwHhcNMTgxMjAzMjIx
NjE4WhcNMjgxMTMwMjIxNjE4WjApMRkwFwYDVQQFExBhOTRmYjRkM2JmMjE2ZDI2
MQwwCgYDVQQMDANURUUwggGiMA0GCSqGSIb3DQEBAQUAA4IBjwAwggGKAoIBgQCm
tuIHkFiy8RtGkKOER60HeGg7CxuvL/tSbA6KsiunVnxQY5036CpuRm4pYnzlPklg
4+AxJ6hTKnHVhmRdUrJg+NwX9/pStjGSu/8veYGK9V2RgbygmDiU42ncuc0GZ/9c
vbER/YM+PGqnAFEmSlBztL/USY0c87IASODyYkad8q1oAMKoEZ1Qs1z6ax5O3ucJ
ZANAre6vxcF1OeEijVO46PXoEzDFIVGMyQPrnD+urWKvvAfH4POi1GR0Am/cyqXU
Y8TXqHcnCGEXV202EUZFna/+JG/pzmzgOuK8AWYUjbU1gQNjp/IHHwZRkhgGj5It
BSLhAH+COXPhZVQFJK0QkAy31ZDTof0nNHfXyIl9oIymtq/LRDXESabl9XbiRApe
X5REDAuBcx1h+N/MhZikwN+UX3zHAxz/OSpix41TzMnW+Jf7I/5FejuFXjaz+gNw
ua02JqLQQDDKCEWbij6/9l04KWjmp3gCHmXXEvJccMMBTtJiQTMbb0jxrm3GLTUC
AwEAAaOBujCBtzAdBgNVHQ4EFgQUVCjAJ9vsQsBQ5ynsSfpSIs4Uf2wwHwYDVR0j
BBgwFoAUTZJAULN6GL+nk7JF4c8HrWP2Y6EwDwYDVR0TAQH/BAUwAwEB/zAOBgNV
HQ8BAf8EBAMCAgQwVAYDVR0fBE0wSzBJoEegRYZDaHR0cHM6Ly9hbmRyb2lkLmdv
b2dsZWFwaXMuY29tL2F0dGVzdGF0aW9uL2NybC8xNTUxMDc0MDg4NjM2NDk1ODc1
MzANBgkqhkiG9w0BAQsFAAOCAgEAlUR6BuceVKtjWkovZ9206dGM++luKCJVGDXN
8fAEf2imX1/lNRiZJLV728n0JZqIaIuE9PbUz+oYlXUD9J6gAYC/kr4HYJS0DNEU
NzkW5NaGZX8ikP341nP0/yd5/N/tKlFf1+ZVu+bxfHYYK+vksrc3++wC1a5V6KFZ
RBSDvkGOZiqa1QbjsedbuqqYJyE3rcxlb2prcw3oE8MVowAH45WhOBQsesAvMXbf
LxaQW2YkWzaNa5QrIDxcELYqsZ1t0B6AlzC7WnRrnbuOxiajyvgRZijyUKBdnlzN
nlTnGvH9HXHF4ce3foYR6OOL+ZcWTXSQmCzMKTv35+shFlAH/0VxU7WdpXtgx0u9
KxYYRBrmplkNN/mPMhJG5OLUcPKs8IabAKyIJRM6QybhvsI1EihH6MEYYpxsPw5/
70sui6tmILVQTLWUp1D+bKVdF3IK5BtT7bwZG7b4t60iTA1/EPa8/kb3J9MEBuVN
4cheu9Rw0CPlcG3JSV81mNYHdfn3TP3XxfpirfGQgJzuP+GwZoTk5QbuyC5uKRqk
PzGQK9/3p0UN+ZeCEBq32re5y02ooGrJim/tlWOq6QyDdPFyLqr2JHifKVZMG/na
CyXd+QLLKwq4h9m8vD02GsyENsvryk8iYJNmra/2DwVtTkUUOczE8FYk9b9fQxok
ZQsTl7Q=
-----END CERTIFICATE-----
                </Certificate>
                <Certificate format="pem">
-----BEGIN CERTIFICATE-----
MIIFfzCCA2egAwIBAgIKA4gmZ2BliZaFyzANBgkqhkiG9w0BAQsFADAbMRkwFwYD
VQQFExBmOTIwMDllODUzYjZiMDQ1MB4XDTE4MTIwMzIyMDMxMloXDTI4MTEzMDIy
MDMxMlowKTEZMBcGA1UEBRMQZjc3ODc5ZWUyNDgwMGE2NjEMMAoGA1UEDAwDVEVF
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAsP/PLNFIWBLsvefdra9l
+fPljnPoF+yO8GWDE7+RFitbrfXJtxwbcO0DMwbPKFsMGywpX4TeVgMAusW8Ippv
QGkYGbxO1aYJ0pW8EDWFrxiHtUQ3stTTrVqtne8r9N77LHoolYNY+DnUqZnP5KI6
nn9ocaU3ajwmBCEY8GIm/IKliR9sMfRq/SXe3vcQeT8KEEDv7hM9GZyf1svn6oWB
+/CJwKlCSYJ0CgAMDIYviQmXWqGuEDZN3a9uIM+Sw2kJ485ZcQY2dXJtv8XT6vuM
CEUb52UWlRBni98zvWXVx8xlEPDUfLXN1lor5kfTxyGSlUnQ5Bkt/7hYHAC5WvVY
ONBv671PYypCwwhcNrL39U0hLR6EFx6o72CCwis0deR+g+iPJL+g4SwgdF4xHHyz
aq+B1KPtwqZ1Z+CFGVrWdixHEQtt69WjSK9jf2biy/D9GhnerXHCU2c6P0Y20Dh5
KAxSArg6UnxsgbRe/coACrJKZEbMVRO8k5WSAErznMD2yhPm8tVqJ4oCew926GUe
wCiNk7lfq7slP3W4Lw6QgQIdABP0ujDnTtpsozyw5M4PU3huMQibzEi3jNCFMG2o
B/6mYCWaSOtxfUE1aSxfMOq0+MOtFWyRSb97T+IsJSUNle/i5VLp6fqHjxb8e1Nl
3FwsPMjf6KeRNYcj2IxjODsCAwEAAaOBtjCBszAdBgNVHQ4EFgQUTZJAULN6GL+n
k7JF4c8HrWP2Y6EwHwYDVR0jBBgwFoAUNmHhAHyIBQlRi0RsR/8aTMnqTxIwDwYD
VR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMCAgQwUAYDVR0fBEkwRzBFoEOgQYY/
aHR0cHM6Ly9hbmRyb2lkLmdvb2dsZWFwaXMuY29tL2F0dGVzdGF0aW9uL2NybC9F
OEZBMTk2MzE0RDJGQTE4MA0GCSqGSIb3DQEBCwUAA4ICAQAgn6xff/xGjDdsAF9i
j2Rp9LiqPACuGPo5MvobmLFrY6pFANJywnJs53xWI4qnzf+ZhAz+ANtVFfdjCVHG
C4EbN14FMI4sht/IWWLejxXumqFsoo7wBTD3X27L0p0iOpVsDC3DavPovEnIWsEm
neHjA4R517nhuoe6wf+btAhViKQvsTw5TsINheY5LiCNkec3AzZlXx5pnnu3rUnP
cI4KSkNWDoMIO8ZYoeQRr1GWb+IJH4ehlYLUmh9ZZEW7BaMDOEAn+AWjvfZDLLza
ej1xQGx5QGmJC2F+its7g93W92shSUCPa+unRNfw7Zrpn2rwNCiFMuz1CnDKVl3q
+IxjcTCdf83OfRJn6vzWLdiR2w5QvN4y7ocSs0yYvR8HafN2gaD3f5FdVj26Crb5
P0zFFJGPp1guFET4Gm0Md1JiEuenc9RC7mcipnazGpesRVa9i0U9I2UJ+eU+FHDs
nInQI5nlsGUUSfrIrGSb5ByVW5TfSFlUBUi43f/QHKorlxWVR1e3xNeN6X2q76ik
3RTbUsMa+YZVKs1ns5di2IxRITiip+H7j4gQxBfRTe7N1AUmgkowy++cXbCaW5Ik
GsNPKyqoG/SuSU/pagqGRnL68LENF2KYPKqaHWJFDMkETqgbrvJmU4020sCMCPG2
tj1z8r50wduWi8iX8wqnowgMWw==
-----END CERTIFICATE-----
                </Certificate>
                <Certificate format="pem">
-----BEGIN CERTIFICATE-----
MIIFHDCCAwSgAwIBAgIJANUP8luj8tazMA0GCSqGSIb3DQEBCwUAMBsxGTAXBgNV
BAUTEGY5MjAwOWU4NTNiNmIwNDUwHhcNMTkxMTIyMjAzNzU4WhcNMzQxMTE4MjAz
NzU4WjAbMRkwFwYDVQQFExBmOTIwMDllODUzYjZiMDQ1MIICIjANBgkqhkiG9w0B
AQEFAAOCAg8AMIICCgKCAgEAr7bHgiuxpwHsK7Qui8xUFmOr75gvMsd/dTEDDJdS
Sxtf6An7xyqpRR90PL2abxM1dEqlXnf2tqw1Ne4Xwl5jlRfdnJLmN0pTy/4lj4/7
tv0Sk3iiKkypnEUtR6WfMgH0QZfKHM1+di+y9TFRtv6y//0rb+T+W8a9nsNL/ggj
nar86461qO0rOs2cXjp3kOG1FEJ5MVmFmBGtnrKpa73XpXyTqRxB/M0n1n/W9nGq
C4FSYa04T6N5RIZGBN2z2MT5IKGbFlbC8UrW0DxW7AYImQQcHtGl/m00QLVWutHQ
oVJYnFPlXTcHYvASLu+RhhsbDmxMgJJ0mcDpvsC4PjvB+TxywElgS70vE0XmLD+O
JtvsBslHZvPBKCOdT0MS+tgSOIfga+z1Z1g7+DVagf7quvmag8jfPioyKvxnK/Eg
sTUVi2ghzq8wm27ud/mIM7AY2qEORR8Go3TVB4HzWQgpZrt3i5MIlCaY504LzSRi
igHCzAPlHws+W0rB5N+er5/2pJKnfBSDiCiFAVtCLOZ7gLiMm0jhO2B6tUXHI/+M
RPjy02i59lINMRRev56GKtcd9qO/0kUJWdZTdA2XoS82ixPvZtXQpUpuL12ab+9E
aDK8Z4RHJYYfCT3Q5vNAXaiWQ+8PTWm2QgBR/bkwSWc+NpUFgNPN9PvQi8WEg5Um
AGMCAwEAAaNjMGEwHQYDVR0OBBYEFDZh4QB8iAUJUYtEbEf/GkzJ6k8SMB8GA1Ud
IwQYMBaAFDZh4QB8iAUJUYtEbEf/GkzJ6k8SMA8GA1UdEwEB/wQFMAMBAf8wDgYD
VR0PAQH/BAQDAgIEMA0GCSqGSIb3DQEBCwUAA4ICAQBOMaBc8oumXb2voc7XCWnu
XKhBBK3e2KMGz39t7lA3XXRe2ZLLAkLM5y3J7tURkf5a1SutfdOyXAmeE6SRo83U
h6WszodmMkxK5GM4JGrnt4pBisu5igXEydaW7qq2CdC6DOGjG+mEkN8/TA6p3cno
L/sPyz6evdjLlSeJ8rFBH6xWyIZCbrcpYEJzXaUOEaxxXxgYz5/cTiVKN2M1G2ok
QBUIYSY6bjEL4aUN5cfo7ogP3UvliEo3Eo0YgwuzR2v0KR6C1cZqZJSTnghIC/vA
D32KdNQ+c3N+vl2OTsUVMC1GiWkngNx1OO1+kXW+YTnnTUOtOIswUP/Vqd5SYgAI
mMAfY8U9/iIgkQj6T2W6FsScy94IN9fFhE1UtzmLoBIuUFsVXJMTz+Jucth+IqoW
Fua9v1R93/k98p41pjtFX+H8DslVgfP097vju4KDlqN64xV1grw3ZLl4CiOe/A91
oeLm2UHOq6wn3esB4r2EIQKb6jTVGu5sYCcdWpXr0AUVqcABPdgL+H7qJguBw09o
jm6xNIrw2OocrDKsudk/okr/AwqEyPKw9WnMlQgLIKw1rODG2NvU9oR3GVGdMkUB
ZutL8VuFkERQGt6vQ2OCw0sV47VMkuYbacK/xyZFiRcrPJPb41zgbQj9XAEyLKCH
ex0SdDrx+tWUDqG8At2JHA==
-----END CERTIFICATE-----
                </Certificate>
            </CertificateChain>
        </Key>
    </Keybox>
</AndroidAttestation>'

    check_root

    if [ ! -d "/data/adb/modules/tricky_store" ] && [ ! -d "/data/adb/modules_update/tricky_store" ]; then
        echo "❌ Tricky Store 模块未安装"
        exit 1
    fi

    mkdir -p "$TRICKY_DIR"
    if [ -f "$TARGET_FILE" ]; then
        mv "$TARGET_FILE" "$BACKUP_FILE"
    fi

    # 更新失败时恢复原 keybox，避免破坏现场
    RESTORED=0
    restore_backup() {
        if [ -f "$BACKUP_FILE" ] && [ ! -f "$TARGET_FILE" ]; then
            mv "$BACKUP_FILE" "$TARGET_FILE"
            RESTORED=1
        fi
    }

    # GitHub 渠道完整流程（原 GitHub在线更新Keybox.sh 已合并）
    # 失败判定总时长 60s，期间每 10s 输出一次倒计时
    download_file() {
        local url="$1" output="$2"
        if command -v curl >/dev/null 2>&1; then
            curl -sLf --connect-timeout 10 -m 60 --retry 2 -o "$output" "$url"
        elif command -v wget >/dev/null 2>&1; then
            wget -T 60 --no-check-certificate -q -O "$output" "$url"
        elif command -v busybox >/dev/null 2>&1; then
            busybox wget -T 60 --no-check-certificate -q -O "$output" "$url"
        else
            return 1
        fi
    }

    update_from_github() {
        # 后台下载 + 倒计时监控（总时长 60s，每 10s 提示剩余时间）
        download_file "$GITHUB_URL" "$REMOTE_FILE" &
        DL_PID=$!
        elapsed=0
        while kill -0 "$DL_PID" 2>/dev/null; do
            sleep 10
            kill -0 "$DL_PID" 2>/dev/null || break
            elapsed=$((elapsed + 10))
            if [ "$elapsed" -ge 60 ]; then
                kill "$DL_PID" 2>/dev/null
                rm -f "$REMOTE_FILE" "$DECODE_FILE"
                return 1
            fi
            echo "下载中，剩余 $((60 - elapsed)) 秒"
        done
        wait "$DL_PID" 2>/dev/null
        if [ -s "$REMOTE_FILE" ] \
            && base64 -d "$REMOTE_FILE" > "$DECODE_FILE" 2>/dev/null \
            && grep -q "AndroidAttestation" "$DECODE_FILE" 2>/dev/null; then
            mv "$DECODE_FILE" "$TARGET_FILE"
            rm -f "$REMOTE_FILE"
            return 0
        fi
        rm -f "$REMOTE_FILE" "$DECODE_FILE"
        return 1
    }

    update_from_local() {
        echo "$LOCAL_KEYBOX" > "$TARGET_FILE"
    }

    SOURCE=""

    case "$CHANNEL" in
        github)
            if update_from_github; then
                SOURCE="GitHub"
            else
                restore_backup
                if [ "$RESTORED" = "1" ]; then
                    echo "❌ GitHub 渠道更新失败，已恢复原 keybox"
                else
                    echo "❌ GitHub 渠道更新失败，请检查网络后重试"
                fi
                exit 1
            fi
            ;;
        local)
            update_from_local
            SOURCE="程序内置"
            ;;
        auto)
            if update_from_github; then
                SOURCE="GitHub"
            else
                update_from_local
                SOURCE="程序内置"
            fi
            ;;
        *)
            restore_backup
            echo "❌ 用法: keybox [github|local]"
            exit 1
            ;;
    esac

    if [ -f "$TARGET_FILE" ]; then
        echo "✅ Keybox 更新成功（来源：$SOURCE）"
    else
        restore_backup
        echo "❌ 更新失败，未生成 keybox.xml"
        exit 1
    fi

    exit 0
}

# =====================================================
# 功能: clean-usb - 清理USB调试痕迹
# =====================================================
cmd_clean_usb() {
    check_root

    settings put global adb_enabled 0 2>/dev/null
    stop adbd 2>/dev/null
    killall -9 adbd adb 2>/dev/null

    RESETPROP=$(find_resetprop)
    if [ -n "$RESETPROP" ]; then
        $RESETPROP --delete persist.service.adb.enable 2>/dev/null
        $RESETPROP --delete persist.service.debuggable 2>/dev/null
        $RESETPROP --delete persist.sys.usb.config 2>/dev/null
        $RESETPROP --delete persist.adb.notify 2>/dev/null
        $RESETPROP ro.debuggable 0 2>/dev/null
        $RESETPROP ro.secure 1 2>/dev/null
        $RESETPROP ro.adb.secure 1 2>/dev/null
    fi

    PERSIST_PROP="/data/property/persistent_properties"
    if [ -f "$PERSIST_PROP" ]; then
        cp "$PERSIST_PROP" "${PERSIST_PROP}.bak.usbclean" 2>/dev/null
        sed -i '/persist\.service\.adb\.enable/d' "$PERSIST_PROP" 2>/dev/null
        sed -i '/persist\.service\.debuggable/d' "$PERSIST_PROP" 2>/dev/null
        sed -i '/persist\.sys\.usb\.config/d' "$PERSIST_PROP" 2>/dev/null
        sed -i '/persist\.adb\./d' "$PERSIST_PROP" 2>/dev/null
    fi

    rm -rf /data/misc/adb/* 2>/dev/null
    rm -rf /data/system/users/*/usb_device_manager.xml 2>/dev/null
    rm -rf /data/user/*/misc/adb/* 2>/dev/null
    rm -rf /data/local/tmp/adb* /data/local/tmp/*.apk /data/local/tmp/*.tmp /data/local/tmp/*.log 2>/dev/null
    rm -rf /data/system/adb* /data/system/usb* 2>/dev/null
    logcat -b all -c 2>/dev/null
    rm -rf /data/system/dropbox/*usb* /data/system/dropbox/*adb* /data/system/dropbox/*debug* 2>/dev/null

    echo "✅ USB调试痕迹清理完成"
    exit 0
}

# =====================================================
# 功能: ts-pkg - 更新TS包名列表
# 修复: /dev/shm 在部分设备不可写，临时文件改用 /data/local/tmp
# 输出: 更新：系统应用/用户应用/总包名 数量
# =====================================================
cmd_ts_pkg() {
    TARGET_DIR="/data/adb/tricky_store"
    TARGET_FILE="${TARGET_DIR}/target.txt"
    TEMP_FILE="/data/local/tmp/bszip_target_temp.txt"

    error_exit() {
        echo "❌ $1"
        rm -f "$TEMP_FILE"
        exit 1
    }

    check_root
    mkdir -p "$TARGET_DIR" || error_exit "目录创建失败"
    [ -f "$TARGET_FILE" ] || touch "$TARGET_FILE" || error_exit "target.txt 创建失败"

    pm list packages 2>/dev/null | sed 's/^package://' | sort > "$TEMP_FILE"
    [ -s "$TEMP_FILE" ] || error_exit "包名拉取失败，请检查 pm 命令权限"

    SYS_COUNT=$(pm list packages -s 2>/dev/null | wc -l)
    USR_COUNT=$(pm list packages -3 2>/dev/null | wc -l)
    TOTAL_COUNT=$(wc -l < "$TEMP_FILE")

    if ! cmp -s "$TEMP_FILE" "$TARGET_FILE"; then
        cp "$TEMP_FILE" "$TARGET_FILE" || error_exit "target.txt 写入失败"
        chmod 644 "$TARGET_FILE"
    fi
    rm -f "$TEMP_FILE"

    echo "更新："
    echo "系统应用 ${SYS_COUNT} 个"
    echo "用户应用 ${USR_COUNT} 个"
    echo "总包名 ${TOTAL_COUNT} 个"
    exit 0
}

# =====================================================
# 功能: hidden-apps - 配置隐藏应用列表
# 依据: 参考sh脚本/隐藏应用列表还原配置.sh 改造（原 配置.sh 已合并）
# 说明: 配置来源固定为同目录 config.json
#       自动查找 HMA 数据目录 (/data/misc/hide_my_applist_*)
#       写入前自动备份原配置 -> config.json.bak
#       仅写盘(持久化)即完成, HMA 在下次框架启动时自动加载
# 用法: hidden-apps [1]  (1=写入后重启系统框架立即生效)
# =====================================================
cmd_hidden_apps() {
    SRC="${MODDIR}/config.json"

    check_root
    IMMEDIATE="${1:-0}"

    # 校验内置配置文件
    if [ ! -f "$SRC" ]; then
        echo "❌ 配置文件不存在: $SRC"
        exit 1
    fi
    if [ ! -s "$SRC" ]; then
        echo "❌ 配置文件为空: $SRC"
        exit 1
    fi

    HMA_DIR=""
    for d in /data/misc/hide_my_applist_*; do
        [ -d "$d" ] && { HMA_DIR="$d"; break; }
    done
    [ -n "$HMA_DIR" ] || { echo "❌ 未找到 HMA 数据目录"; exit 1; }
    DEST="$HMA_DIR/config.json"

    [ -f "$DEST" ] && cp -a "$DEST" "$HMA_DIR/config.json.bak"
    cp "$SRC" "$DEST"
    chown system:system "$DEST"
    chmod 600 "$DEST"

    if [ "$IMMEDIATE" = "1" ]; then
        sleep 1
        SS=$(pidof system_server)
        [ -n "$SS" ] && kill "$SS"
        echo "配置还原成功，已触发框架重启立即生效。"
    else
        echo "配置还原成功，将在下次框架启动时自动加载此配置。"
    fi
    exit 0
}

# =====================================================
# 功能: hide-root - 一键配置隐藏Root
# =====================================================
cmd_hide_root() {
    linker_FILE="/data/adb/zygisksu/linker"
    POLICY_FILE="/data/adb/zygisksu/denylist_policy"
    ENFORCE_FILE="/data/adb/zygisksu/denylist_enforce"
    MEM_FILE="/data/adb/zygisksu/memory_type"

    [ -f "$linker_FILE" ] || touch "$linker_FILE"
    [ -f "$ENFORCE_FILE" ] || touch "$ENFORCE_FILE"
    [ -f "$POLICY_FILE" ] || touch "$POLICY_FILE"
    [ -f "$MEM_FILE" ] || touch "$MEM_FILE"

    current_policy=$(cat "$linker_FILE")
    [ "$current_policy" != "1" ] && echo "1" > "$linker_FILE"

    current_policy=$(cat "$POLICY_FILE")
    [ "$current_policy" != "1" ] && echo "1" > "$POLICY_FILE"

    current_enforce=$(cat "$ENFORCE_FILE")
    [ "$current_enforce" != "2" ] && echo "2" > "$ENFORCE_FILE"

    current_mem=$(cat "$MEM_FILE")
    [ "$current_mem" != "1" ] && echo "1" > "$MEM_FILE"

    echo "✅ 全局隐藏Root已开启，重启生效"
}

# =====================================================
# 功能: fix-network - 修复越狱后无网络
# 来源: 参考sh脚本/网络修复.sh
# 流程: 重载 SELinux 策略 -> 飞行模式开关重置网络
# =====================================================
cmd_fix_network() {
    check_root
    KSU_BB="/data/adb/ksu/bin/busybox"
    OK=0

    if [ -x "$KSU_BB" ] && "$KSU_BB" --list 2>/dev/null | grep -q "load_policy"; then
        "$KSU_BB" load_policy /sys/fs/selinux/policy 2>/dev/null && OK=1
    elif command -v load_policy >/dev/null 2>&1; then
        load_policy /sys/fs/selinux/policy 2>/dev/null && OK=1
    else
        /system/bin/load_policy /sys/fs/selinux/policy 2>/dev/null && OK=1
    fi

    if [ "$OK" = "1" ]; then
        cmd connectivity airplane-mode enable 2>/dev/null
        sleep 1
        cmd connectivity airplane-mode disable 2>/dev/null
        echo "✅ 越狱网络修复完成"
    else
        echo "❌ SELinux 策略加载失败"
        exit 1
    fi
}

# =====================================================
# 功能: jailbreak-hide - 越狱隐藏环境（PID 轮回）
# 来源: 参考sh脚本/越狱隐藏.sh
# 流程: PID 轮回（临时压低 pid_max + fork 循环，guard 上限防死循环）
# 警告: 部分机型可能卡死重启
# =====================================================
cmd_jailbreak_hide() {
    check_root

    # PID 轮回：临时压低 pid_max 加速轮回，结束恢复原值（防大 pid_max 机型卡死）
    ORIG_PID_MAX=$(cat /proc/sys/kernel/pid_max)
    [ "$ORIG_PID_MAX" -gt 32768 ] && echo 32768 > /proc/sys/kernel/pid_max 2>/dev/null
    wrapped=0
    last_pid=$(sh -c 'echo $PPID')
    guard=0
    while :; do
        : &
        current_pid=$!
        [ "$current_pid" -lt "$last_pid" ] && wrapped=1
        if [ "$wrapped" -eq 1 ] && [ "$current_pid" -ge 1700 ]; then
            break
        fi
        last_pid=$current_pid
        guard=$((guard + 1))
        [ "$guard" -ge 100000 ] && break
    done
    [ "$ORIG_PID_MAX" -gt 32768 ] && echo "$ORIG_PID_MAX" > /proc/sys/kernel/pid_max 2>/dev/null

    echo "✅ 越狱环境隐藏完成"
    exit 0
}

# =====================================================
# 功能: hash - 重置哈希值
# =====================================================
cmd_hash() {
    if [ $# -lt 1 ] || [ -z "$1" ]; then
        echo "❌ 请传入哈希值参数"
        exit 1
    fi

    HASH_VALUE="$1"

    if [ -d /data/adb/modules/tricky_store ]; then
        mkdir -p /data/adb/modules/Reset_BootHash
        rm -f /data/adb/modules/Reset_BootHash/service.sh
        rm -f /data/adb/modules/Reset_BootHash/module.prop

        echo "id=Reset_BootHash
name=重置哈希值
version=v2024.09.17
versionCode=20240917
description=每次重启重置哈希值模块" > /data/adb/modules/Reset_BootHash/module.prop

        echo "resetprop -n ro.boot.vbmeta.digest $HASH_VALUE" > /data/adb/modules/Reset_BootHash/service.sh
        chmod 755 /data/adb/modules/Reset_BootHash/service.sh

        echo "✅ 哈希值已设置为: $HASH_VALUE"
        echo "重启手机生效"
    else
        echo "❌ 未安装 Tricky Store 模块"
        exit 1
    fi
}

# =====================================================
# 功能: fix-lsposed - 清理LSPosed Hook痕迹
# =====================================================
cmd_fix_lsposed() {
    find /data/app -type f -name base.odex -delete
    echo "✅ LSPosed Hook痕迹清理完成"
}

# =====================================================
# 功能: fix-recovery - 修复Twrp痕迹
# =====================================================
cmd_fix_recovery() {
    TWRP_FOLDER="/sdcard/TWRP"
    if [ -d "$TWRP_FOLDER" ]; then
        rm -rf "$TWRP_FOLDER"
        echo "✅ TWRP痕迹清理完成"
    else
        echo "✅ 无TWRP痕迹，无需清理"
    fi
}

# =====================================================
# 功能: clean-all - 清理所有痕迹
# =====================================================
cmd_clean_all() {
    detector_data() {
        remove_path "/storage/emulated/0/Android/data/me.garfieldhan.holmes"
        remove_path "/storage/emulated/0/Android/data/com.zhenxi.hunter"
        remove_path "/storage/emulated/0/Android/data/icu.nullptr.nativetest"
        remove_path "/storage/emulated/0/Android/data/icu.nullptr.applistdetector"
        remove_path "/storage/emulated/0/Android/data/com.byxiaorun.detector"
        remove_path "/storage/emulated/0/Android/data/io.github.huskydg.memorydetector"
        remove_path "/storage/emulated/0/Android/data/com.OrangeEnvironment.Detector"
        remove_path "/storage/emulated/0/Android/data/com.Longze.detector.pro2"
        remove_path "/storage/emulated/0/Android/data/rikka.safetynetchecker"
        remove_path "/storage/emulated/0/Android/data/io.github.vvb2060.keyattestation"
        remove_path "/storage/emulated/0/Android/data/io.github.vvb2060.mahoshojo"
        remove_path "/storage/emulated/0/Android/data/com.lingqing.detector"
        remove_path "/storage/emulated/0/Android/data/aidepro.top"
        remove_path "/storage/emulated/0/Android/data/com.junge.algorithmAidePro"
        remove_path "/storage/emulated/0/Android/data/chunqiu.safe"
        remove_path "/storage/emulated/0/Android/data/luna.safe.luna"
        remove_path "/storage/emulated/0/Android/data/io.liankong.riskdetector"
        remove_path "/storage/emulated/0/Android/data/com.studio.duckdetector"
        remove_path "/storage/emulated/0/Android/data/com.android.nativetest"
        remove_path "/storage/emulated/0/Android/data/com.byyoung.setting"
        remove_path "/storage/emulated/0/Android/data/com.scottyab.rootbeer"
        remove_path "/storage/emulated/0/Android/data/com.scottyab.rootbeer.sample"
        remove_path "/storage/emulated/0/Android/data/com.topjohnwu.magisk.detector"
        remove_path "/storage/emulated/0/Android/data/com.devadvance.rootcloak"
        remove_path "/storage/emulated/0/Android/data/com.fde.xposed.detector"
        remove_path "/storage/emulated/0/Android/data/com.zhenxi.checker"
        remove_path "/storage/emulated/0/Android/data/com.example.nativelibtest"
        remove_path "/storage/emulated/0/Android/data/com.example.memcheck"
        remove_path "/storage/emulated/0/Android/data/com.example.syscallchecker"
        remove_path "/storage/emulated/0/Android/data/com.jrummyapps.rootchecker"
        remove_path "/storage/emulated/0/Android/data/com.kimchangyoun.magiskdetector"
        remove_path "/storage/emulated/0/Android/data/com.reveny.nativecheck"
        remove_path "/storage/emulated/0/Android/data/com.reveny.environmentchecker"
        remove_path "/storage/emulated/0/Android/data/com.reveny.rootcheck"
        remove_path "/storage/emulated/0/Android/data/com.guardian.detect"
        remove_path "/storage/emulated/0/Android/data/com.security.environmentchecker"
        remove_path "/storage/emulated/0/Android/data/com.integrity.checker"
        remove_path "/storage/emulated/0/Android/data/com.integrity.attestation"
        remove_path "/storage/emulated/0/Android/data/com.lody.virtual"
        remove_path "/storage/emulated/0/Android/data/com.lody.virtual.client"
        remove_path "/storage/emulated/0/Android/data/com.lody.virtual.server"
        remove_path "/storage/emulated/0/Android/data/com.lody.whale"
        remove_path "/storage/emulated/0/Android/data/com.kimchangyoun.rootbeerfresh"
        remove_path "/storage/emulated/0/Android/data/com.didikee.rootcheck"
        remove_path "/storage/emulated/0/Android/data/com.joeykrim.rootcheck"
        remove_path "/storage/emulated/0/Android/data/com.freeandroidtools.rootchecker"
        remove_path "/storage/emulated/0/Android/data/com.bluestacks.rootchecker"
        remove_path "/storage/emulated/0/Android/data/com.moonshine.checker"
        remove_path "/storage/emulated/0/Android/data/com.ramdroid.appdetector"
        remove_path "/storage/emulated/0/Android/data/com.smlj.rootcheck"
        remove_path "/storage/emulated/0/Android/data/com.devadvance.rootcloakplus"
        remove_path "/storage/emulated/0/Android/data/com.formyhm.hideroot"
        remove_path "/storage/emulated/0/Android/data/com.example.emulatordetector"
        remove_path "/storage/emulated/0/Android/data/com.vmcheck.detector"
        remove_path "/storage/emulated/0/Android/data/com.virtual.checker"
        remove_path "/storage/emulated/0/Android/data/com.antivm.detector"
        remove_path "/storage/emulated/0/Android/data/com.xposed.checker"
        remove_path "/storage/emulated/0/Android/data/com.google.snet.test"
        remove_path "/storage/emulated/0/Android/data/com.attestation.checker"
        remove_path "/storage/emulated/0/Android/data/com.integrity.check"
        remove_path "/storage/emulated/0/Android/data/com.native.checker"
        remove_path "/storage/emulated/0/Android/data/com.syscall.detector"
        remove_path "/storage/emulated/0/Android/data/com.memory.scan"
        remove_path "/storage/emulated/0/meow_detector.log"
        remove_path "/storage/emulated/0/keybox_status.json"
    }

    detector_obb() {
        remove_path "/storage/emulated/0/Android/obb/io.github.vvb2060.mahoshojo"
        remove_path "/storage/emulated/0/Android/obb/icu.nullptr.applistdetector"
        remove_path "/storage/emulated/0/Android/obb/icu.nullptr.nativetest"
        remove_path "/storage/emulated/0/Android/obb/com.byxiaorun.detector"
        remove_path "/storage/emulated/0/Android/obb/io.github.huskydg.memorydetector"
        remove_path "/storage/emulated/0/Android/obb/com.OrangeEnvironment.Detector"
        remove_path "/storage/emulated/0/Android/obb/com.Longze.detector.pro2"
        remove_path "/storage/emulated/0/Android/obb/rikka.safetynetchecker"
        remove_path "/storage/emulated/0/Android/obb/io.github.vvb2060.keyattestation"
        remove_path "/storage/emulated/0/Android/obb/com.android.nativetest"
    }

    detector_media() {
        remove_path "/storage/emulated/0/Android/media/icu.nullptr.nativetest"
    }

    tool_apps_data() {
        remove_path "/storage/emulated/0/Android/data/bin.mt.plus"
        remove_path "/storage/emulated/0/Android/data/bin.mt.plus.canary"
        remove_path "/storage/emulated/0/Android/data/com.omarea.vtools"
        remove_path "/storage/emulated/0/Android/data/moe.shizuku.privileged.api"
        remove_path "/storage/emulated/0/Android/data/com.estrongs.android.pop"
        remove_path "/storage/emulated/0/Android/data/com.coolapk.market"
        remove_path "/storage/emulated/0/MT2"
        remove_path "/storage/emulated/0/bin.mt.termux"
        remove_path "/storage/emulated/0/com.termux"
        remove_path "/storage/emulated/0/xzr.hkf"
        remove_path "/storage/emulated/0/Download/WechatXposed"
        remove_path "/storage/emulated/0/WechatXposed"
        remove_path "/storage/emulated/0/Android/naki"
        remove_path "/storage/emulated/0/最新版隐藏配置.json"
        remove_path "/storage/emulated/0/rlgg"
        remove_path "/storage/emulated/legacy"
        remove_path "/storage/emulated/com.luckyzyx.luckytool"
        remove_path "/storage/emulated/0/Android/data/com.sevtinge.hyperceiler"
        remove_path "/storage/emulated/0/Android/data/com.coderstory.toolkit"
    }

    remote_control_data_apps() {
        remove_path "/storage/emulated/0/.anydesk"
        remove_path "/storage/emulated/0/Android/data/com.anydesk.anydeskandroid"
        remove_path "/storage/emulated/0/Android/data/com.teamviewer.teamviewer.market.mobile"
        remove_path "/storage/emulated/0/Android/data/com.teamviewer.quicksupport.market"
        remove_path "/storage/emulated/0/Android/data/com.sand.airdroid"
        remove_path "/storage/emulated/0/Android/data/com.sand.airmirror"
        remove_path "/storage/emulated/0/Android/data/com.koushikdutta.vysor"
        remove_path "/storage/emulated/0/Android/data/com.genymobile.scrcpy"
        remove_path "/storage/emulated/0/anydesk"
        remove_path "/storage/emulated/0/Android/data/com.microsoft.rdc.androidx"
        remove_path "/storage/emulated/0/Android/data/com.realvnc.viewer.android"
        remove_path "/storage/emulated/0/Android/data/com.splashtop.remote.pad.v2"
        remove_path "/storage/emulated/0/Android/data/com.dwservice.dwagent"
        remove_path "/storage/emulated/0/Android/data/com.carriez.flutter_hbb"
        remove_path "/storage/emulated/0/Android/data/com.carriez.flutter_hbbclient"
        remove_path "/storage/emulated/0/Android/data/com.rustdesk.rustdesk"
        remove_path "/storage/emulated/0/.rustdesk"
        remove_path "/storage/emulated/0/rustdesk"
        remove_path "/storage/emulated/0/Android/media/com.koushikdutta.vysor"
        remove_path "/storage/emulated/0/.vysor"
        remove_path "/storage/emulated/0/Vysor"
    }

    system_properties() {
        remove_path "/data/property/persistent_properties"
        remove_path "/data/property"
    }

    tmp_data() {
        remove_path "/data/local/tmp/shizuku"
        remove_path "/data/local/tmp/shizuku_starter"
        remove_path "/data/local/tmp/byyang"
        remove_path "/data/local/tmp/HyperCeiler"
        remove_path "/data/local/tmp/luckys"
        remove_path "/data/local/tmp/input_devices"
        remove_path "/data/local/tmp/resetprop"
        rm -rf /data/local/tmp/* 2>/dev/null
        mkdir -p /data/local/tmp 2>/dev/null
    }

    system_data() {
        remove_path "/data/system/graphicsstats"
        remove_path "/data/system/package_cache"
        remove_path "/data/system/NoActive"
        remove_path "/data/system/Freezer"
        remove_path "/data/system/junge"
        remove_path "/data/swap_config.conf"
    }

    dev_paths() {
        remove_path "/dev/memcg/scene_idle"
        remove_path "/dev/memcg/scene_active"
        remove_path "/dev/scene"
        remove_path "/dev/cpuset/scene-daemon"
    }

    user_data() {
        remove_path "/data/user/0/com.juom"
    }

    reset_prop() {
        while [ "$(getprop sys.boot_completed)" != "1" ]; do
            sleep 1
        done
        resetprop sys.usb.adb.disabled 1
        resetprop persist.sys.usb.config mtp
        resetprop sys.usb.config mtp
        resetprop sys.usb.state mtp
        resetprop service.adb.root 0
        resetprop service.adb.tcp.port -1
        resetprop --delete persist.service.adb.enable
        resetprop --delete persist.service.debuggable
        resetprop --delete persist.zygote.app_data_isolation
        resetprop --delete persist.hyperceiler.log.level
        resetprop --delete persist.com.luckyzyx.luckytool.log.level
        resetprop --delete persist.com.luckyzyx.luckytool.debug
        resetprop --delete persist.com.luckyzyx.luckytool.enable
        resetprop persist.sys.developer_options 0
        resetprop persist.sys.dev_mode 0
        resetprop persist.sys.debuggable 0
        settings put global development_settings_enabled 0
        settings put global adb_enabled 0
        settings put global oem_unlock_allowed 0
        settings put global adb_wifi_enabled 0
        settings put global adb_wifi_port -1
        resetprop ro.debuggable 0
        resetprop ro.secure 1
        resetprop ro.adb.secure 1
        resetprop ro.build.type user
        resetprop ro.build.tags release-keys
        resetprop --delete persist.sys.developer_options
        resetprop --delete persist.sys.dev_mode
        resetprop ro.boot.verifiedbootstate green
        resetprop vendor.boot.verifiedbootstate green
        resetprop ro.boot.flash.locked 1
        resetprop ro.boot.vbmeta.device_state locked
        resetprop vendor.boot.vbmeta.device_state locked
        resetprop ro.secureboot.lockstate locked
        resetprop ro.boot.warranty_bit 0
        resetprop ro.boot.force_normal_boot 1
        resetprop ro.boot.realme.lockstate 1
        resetprop ro.boot.flash.locked 1
        resetprop ro.boot.verifiedbootstate green
        resetprop ro.boot.vbmeta.device_state locked
        resetprop ro.boot.secureboot 1
        resetprop ro.boot.veritymode enforcing
        resetprop ro.boot.verifiedbootstate green
        resetprop ro.boot.vbmeta.device_state locked
        resetprop ro.boot.secureboot enabled
        resetprop ro.oem_unlock_supported 0
        resetprop sys.oem_unlock_allowed 0
        if [ "$(getenforce 2>/dev/null)" = "Enforcing" ]; then
            resetprop ro.boot.selinux enforcing
            resetprop ro.build.selinux 1
        fi
        resetprop ro.kernel.qemu 0
        resetprop ro.boot.qemu 0
        resetprop ro.hardware.virtual_device 0
    }

    odex_files() {
        su -c 'find /data/app -type f -name base.odex -delete' 2>/dev/null
    }

    detector_data
    detector_obb
    detector_media
    tool_apps_data
    remote_control_data_apps
    system_properties
    tmp_data
    system_data
    dev_paths
    user_data
    reset_prop
    odex_files
    echo "✅ 所有痕迹清理完成"
}

# =====================================================
# 功能: clean-luna / fix-niutou - 清理Luna和牛头11异常
# =====================================================
cmd_clean_luna() {
    if [ "$(id -u)" != "0" ]; then
        echo "❌ 需要 Root 权限"
        exit 1
    fi

    targets=(
        "/data/nh/"
        "/data/nh5/"
        "/data/nh6/"
        "/data/nh2/"
        "/data/nh3/"
        "/data/nh4/"
        "/data/nh.ko"
        "/data/gamepad_driver.so"
        "/sdcard/elgg/"
        "/data/BingPUBG/"
        "/data/BingHPJY/"
        "/data/jz/"
        "/data/jz.sh"
        "/data/system/liboxmem.so"
        "/data/local/tmp/gamepad_driver.so"
        "/system/lib/hid/gamepad_driver.so"
        "/data/.gamepad_driver_installed"
        "/data/system/liborangeinit.so"
        "/data/system/xydriver.ko"
        "/data/BingPUBG/guns.cfg"
        "/data/BingHPJY/pz.cfg"
        "/dev/Bing/"
        "/data/单发枪配置.txt"
        "/data/local/tmp/单发枪配置.txt"
        "/data/A内核.ini"
        "/data/物资.txt"
        "/data/HPX/"
        "/data/HPY/"
        "/data/system/HPX/"
        "/data/system/HPY/"
        "/storage/emulated/0/落叶配置/"
        "/storage/emulated/0/BY物资/"
        "/storage/emulated/0/落叶配置/落叶配置.txt"
        "/storage/emulated/0/BY物资/BY物资.txt"
        "/storage/emulated/elgg/"
        "/storage/emulated/0/Download/WechatXposed/"
        "/storage/emulated/legacy/Android/data/com.apocalua.run/"
        "/storage/emulated/0/BY物资/BY物资.txt"
    )

    deleted_count=0
    for target in "${targets[@]}"; do
        if [ -e "$target" ]; then
            if [ -d "$target" ]; then
                rm -rf "$target"
            else
                rm -f "$target"
            fi
            ((deleted_count++))
        fi
    done

    echo "✅ 清理完成，共删除 $deleted_count 个目标"
}

# =====================================================
# 功能: fix-chunqiu - 修复春秋Found property
# =====================================================
cmd_fix_chunqiu() {
    setprop persist.logd.size ""
    setprop persist.logd.size.crash ""
    setprop persist.logd.size.system ""
    setprop persist.logd.size.main ""
    echo "✅ 修复成功"
}

# =====================================================
# 功能: fix-momo - 修复Momo SDK
# =====================================================
cmd_fix_momo() {
    settings delete global hidden_api_policy >/dev/null 2>&1
    settings delete global hidden_api_policy_p_apps >/dev/null 2>&1
    settings delete global hidden_api_policy_pre_p_apps >/dev/null 2>&1
    settings delete global hidden_api_blacklist_exemptions >/dev/null 2>&1
    killall -9 io.github.vvb2060.mahoshojo >/dev/null 2>&1
    am force-stop io.github.vvb2060.mahoshojo >/dev/null 2>&1
    am kill io.github.vvb2060.mahoshojo >/dev/null 2>&1
    echo "✅ Momo检测修复完成"
}

# =====================================================
# 功能: fix-hunter - 修复Hunter API
# =====================================================
cmd_fix_hunter() {
    check_root
    settings delete global hidden_api_policy >/dev/null 2>&1
    settings delete global hidden_api_policy_p_apps >/dev/null 2>&1
    settings delete global hidden_api_policy_pre_p_apps >/dev/null 2>&1
    settings delete global hidden_api_blacklist_exemptions >/dev/null 2>&1
    echo "✅ Hunter API 修复成功"
}

# =====================================================
# 功能: clean-traces - 清理USB和玩机痕迹（合并执行）
# 合并: fix-recovery + clean-all + clean-luna + fix-chunqiu
#       + fix-momo + fix-hunter + clean-usb
# 说明: 各步骤以子 shell 执行且静默，单步失败不影响后续步骤
# 输出: 仅最终一行汇总
# =====================================================
cmd_clean_traces() {
    check_root

    (cmd_fix_recovery >/dev/null)
    (cmd_clean_all >/dev/null)
    (cmd_clean_luna >/dev/null)
    (cmd_fix_chunqiu >/dev/null)
    (cmd_fix_momo >/dev/null)
    (cmd_fix_hunter >/dev/null)
    (cmd_clean_usb >/dev/null)

    echo "✅ USB和玩机痕迹清理完成"
    exit 0
}

# =====================================================
# 功能: tee-burn - TEE烧录密钥
# =====================================================
cmd_tee_burn() {
    KEYBOX_FILE="/data/adb/tricky_store/keybox.xml"
    TEMP_FILE="/data/local/tmp/LING"

    if [ ! -f "$KEYBOX_FILE" ]; then
        echo "❌ 未找到 keybox.xml，请先更新 Keybox"
        exit 1
    fi

    if [ ! -f "/vendor/bin/KmInstallKeybox" ]; then
        echo "❌ 未找到 KmInstallKeybox 工具"
        exit 1
    fi

    cat "$KEYBOX_FILE" | \
        sed 's/<\?xml version="1.0"[^?]*\?>/<?xml version="1.0"?>/g' | \
        sed 's/<Keybox DeviceID="[^"]*">/<Keybox DeviceID="LING">/g' \
        > "$TEMP_FILE"

    if [ ! -s "$TEMP_FILE" ]; then
        echo "❌ Keybox 处理失败"
        exit 1
    fi

    LD_LIBRARY_PATH=/vendor/lib64/hw /vendor/bin/KmInstallKeybox "$TEMP_FILE" LING true >/dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✅ TEE烧录成功"
        rm -f "$TEMP_FILE"
    else
        echo "❌ TEE烧录失败"
        exit 1
    fi
}

# =====================================================
# 功能: usb-check - USB状态检测
# =====================================================
cmd_usb_check() {
    ADB_VAL=$(settings get global adb_enabled 2>/dev/null)
    SEC_VAL=$(getprop persist.security.adbinput 2>/dev/null)
    [ "$ADB_VAL" = "1" ] && ADB_ST=1 || ADB_ST=0
    [ "$SEC_VAL" = "1" ] && SEC_ST=1 || SEC_ST=0
    echo "${ADB_ST}${SEC_ST}"
}

# =====================================================
# 功能: usb-switch - USB开关控制
# 用法: usb-switch [adb|secure] [0|1]
# =====================================================
cmd_usb_switch() {
    if [ $# -lt 2 ]; then
        echo "用法: $0 usb-switch [adb|secure] [0|1]"
        exit 1
    fi

    TARGET="$1"
    VALUE="$2"

    case "$TARGET" in
        adb)
            if [ "$VALUE" = "1" ]; then
                settings put global adb_enabled 1
                echo "USB调试已开启"
            else
                settings put global adb_enabled 0
                echo "USB调试已关闭"
            fi
            ;;
        secure)
            if [ "$VALUE" = "1" ]; then
                setprop persist.security.adbinput 1
                echo "USB调试（安全设置）已开启"
            else
                setprop persist.security.adbinput 0
                echo "USB调试（安全设置）已关闭"
            fi
            ;;
        *)
            echo "未知目标: $TARGET，只支持 adb 或 secure"
            exit 1
            ;;
    esac
}

# =====================================================
# 功能: soft-reboot - 软重启（重启 Zygote）
# 依据: 参考sh脚本/softreboot.sh 档位 2
# 效果: zygote 及其派生进程全部重建，App 全部重启
#       重载 Zygisk/LSPosed 注入和激活大部分模块
#       /data 不动、属性存储保留、adb 不断线、内核/BL 不参与
# 成功判定: boot_id 不变 + system_server PID 改变
# =====================================================
cmd_soft_reboot() {
    check_root

    ZG_PIDS=$(pidof zygote zygote64 2>/dev/null)
    if [ -z "$ZG_PIDS" ]; then
        echo "❌ 未找到 zygote 进程，当前系统状态不适合软重启"
        exit 1
    fi

    OLD_BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
    OLD_SYS_PID=$(pidof system_server 2>/dev/null)

    echo "[*] 正在软重启（重启 Zygote）..."
    setprop ctl.restart zygote 2>/dev/null || killall zygote 2>/dev/null || killall zygote64 2>/dev/null

    i=0
    NEW_SYS_PID=""
    while [ $i -lt 60 ]; do
        NEW_SYS_PID=$(pidof system_server 2>/dev/null)
        BOOTED=$(getprop sys.boot_completed 2>/dev/null)
        if [ -n "$NEW_SYS_PID" ] && [ "$NEW_SYS_PID" != "$OLD_SYS_PID" ] && [ "$BOOTED" = "1" ]; then
            break
        fi
        sleep 2; i=$((i+2))
    done

    NEW_BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
    if [ "$NEW_BOOT_ID" = "$OLD_BOOT_ID" ] && [ -n "$NEW_SYS_PID" ] && [ "$NEW_SYS_PID" != "$OLD_SYS_PID" ]; then
        echo "✅ 软重启完成，Zygisk/LSPosed 注入已重载"
        exit 0
    else
        echo "⚠️ 未能在超时时间内确认完成，可稍后手动检查设备状态"
        exit 1
    fi
}

# =====================================================
# 功能: deep-reboot - 深度软重启（加强 · 用户态重启）
# 依据: 参考sh脚本/softreboot.sh 档位 3
# 效果: /data 卸载后重新挂载；属性存储重建
#       适合加载系统属性修改（如改机型模块）
#       内核/BL 不参与（boot_id 不变）；adb 与 WebUI 将断开需重连
# 耗时: 约 1~3 分钟
# =====================================================
cmd_deep_reboot() {
    check_root

    if [ -z "$(pidof zygote zygote64 2>/dev/null)" ]; then
        echo "❌ 未找到 zygote 进程，当前系统状态不适合软重启"
        exit 1
    fi

    echo "✅ 深度软重启已触发，连接将断开，约1~3分钟后请重新打开本界面"
    sleep 3
    setprop sys.powerctl userdata_reboot
    exit 0
}

# =====================================================
# 功能: status - Root管理器与BL锁真实状态检测（供 WebUI 首页头部调用）
# 依据: 参考sh脚本/真实设备BL状态.sh (bltruth 完整取证方式)
# 输出: ROOT= / BL=unlocked|locked|unknown 键值对
# 取证: [1] 内核直通证据(/proc/bootconfig > /proc/cmdline > device-tree) 真相源
#       [2] 属性存储声明(getprop ro.boot.*) 可伪造层, 仅作对照组
#       [3] vbmeta 分区裸 flags(偏移120,4字节) 物理铁证, 取末字节裁决
#       [5] 交叉验证: 真相源 vs 属性声明逐项比对, 矛盾即检出属性伪造
#       [6] 裁决(让离内核最近的层当裁判):
#           真相源=unlocked                        -> UNLOCKED(无论属性如何伪装)
#           真相源=locked 且无伪造 且flags末字节=00
#             且属性侧一致(green/locked)           -> LOCKED
#           真相源=locked 但属性矛盾(检出伪造)      -> UNLOCKED
#           flags 非零(验证被刷写关闭,仅解锁后可行) -> UNLOCKED
#           真相源缺失但属性矛盾且声称locked/green  -> UNLOCKED
#           所有真相源均不可得                      -> 诚实返回 unknown
# =====================================================
cmd_status() {
    # Root 管理器识别
    if [ -d "/data/adb/ksu" ] || [ -f "/data/adb/ksud" ]; then
        echo "ROOT=KernelSU"
    elif [ -d "/data/adb/ap" ] || [ -f "/data/adb/apd" ]; then
        echo "ROOT=APatch"
    elif [ -d "/data/adb/magisk" ]; then
        echo "ROOT=Magisk"
    else
        echo "ROOT=unknown"
    fi

    # ---------- 缓存底层原始数据（直读失败时经 su 提权重试） ----------
    R=0
    [ "$(id -u)" = "0" ] && R=1

    BC_RAW=""
    CMD_RAW=""
    if [ -r /proc/bootconfig ]; then
        BC_RAW=$(cat /proc/bootconfig 2>/dev/null)
    fi
    if [ -z "$BC_RAW" ] && command -v su >/dev/null 2>&1; then
        BC_RAW=$(su -c "cat /proc/bootconfig" 2>/dev/null)
    fi
    if [ -r /proc/cmdline ]; then
        CMD_RAW=$(cat /proc/cmdline 2>/dev/null)
    fi
    if [ -z "$CMD_RAW" ] && command -v su >/dev/null 2>&1; then
        CMD_RAW=$(su -c "cat /proc/cmdline" 2>/dev/null)
    fi

    val_bc() {
        echo "$BC_RAW" | grep -a "^$1 *=" | head -n 1 \
            | sed -e 's/^[^=]*= *//' -e 's/^"//' -e 's/"$//'
    }
    val_cmd() {
        echo "$CMD_RAW" | tr ' ' '\n' | grep -a "^$1=" \
            | head -n 1 | cut -d= -f2-
    }
    val_dt() {
        [ -f "$1" ] && tr -d '\000' < "$1" 2>/dev/null
    }

    # ---------- [1] 内核直通证据 ----------
    bc_dev=$(val_bc androidboot.vbmeta.device_state)
    bc_vbs=$(val_bc androidboot.verifiedbootstate)
    bc_lk=$(val_bc androidboot.flash.locked)
    cmd_dev=$(val_cmd androidboot.vbmeta.device_state)
    cmd_vbs=$(val_cmd androidboot.verifiedbootstate)
    cmd_lk=$(val_cmd androidboot.flash.locked)
    dt_dev=$(val_dt /proc/device-tree/firmware/android/vbmeta.device_state)
    dt_lk=$(val_dt /proc/device-tree/firmware/android/flash.locked)

    TRUE_DEV=""
    TRUE_VBS=""
    TRUE_LK=""
    if [ -n "$bc_dev" ]; then
        TRUE_DEV="$bc_dev"; TRUE_VBS="$bc_vbs"; TRUE_LK="$bc_lk"
    elif [ -n "$cmd_dev" ]; then
        TRUE_DEV="$cmd_dev"; TRUE_VBS="$cmd_vbs"; TRUE_LK="$cmd_lk"
    elif [ -n "$dt_dev" ]; then
        TRUE_DEV="$dt_dev"; TRUE_LK="$dt_lk"
    fi

    # ---------- [2] vbmeta 分区原始 flags（物理铁证，取末字节裁决） ----------
    slot=$(getprop ro.boot.slot_suffix)
    node=""
    FLAGS_HEX=""
    for b in /dev/block/by-name /dev/block/bootdevice/by-name; do
        if [ -e "$b/vbmeta$slot" ]; then node="$b/vbmeta$slot"; break; fi
        if [ -e "$b/vbmeta" ]; then node="$b/vbmeta"; break; fi
    done
    if [ -z "$node" ] && [ "$R" = "1" ]; then
        node=$(find /dev/block -maxdepth 4 \( -iname "vbmeta$slot" -o -iname "vbmeta" \) 2>/dev/null | head -n 1)
    fi
    if [ -n "$node" ]; then
        if [ "$R" = "1" ]; then
            FLAGS_HEX=$(dd if="$node" bs=1 skip=120 count=4 2>/dev/null | od -A n -t x1 | tr -d ' \n')
        elif command -v su >/dev/null 2>&1; then
            FLAGS_HEX=$(su -c "dd if=$node bs=1 skip=120 count=4" 2>/dev/null | od -A n -t x1 | tr -d ' \n')
        fi
    fi
    LAST_FLAGS="${FLAGS_HEX#??????}"

    # ---------- [5] 交叉验证：真相源 vs 属性声明（getprop 可伪造对照组） ----------
    p_dev=$(getprop ro.boot.vbmeta.device_state)
    p_vbs=$(getprop ro.boot.verifiedbootstate)
    p_lk=$(getprop ro.boot.flash.locked)

    td=$(echo "$TRUE_DEV" | tr 'A-Z' 'a-z')
    pd=$(echo "$p_dev" | tr 'A-Z' 'a-z')
    tv=$(echo "$TRUE_VBS" | tr 'A-Z' 'a-z')
    pv=$(echo "$p_vbs" | tr 'A-Z' 'a-z')
    tl=$(echo "$TRUE_LK" | tr -d ' \t')
    pl=$(echo "$p_lk" | tr -d ' \t')

    SPOOF="NO"
    if [ -n "$td" ] && [ -n "$pd" ] && [ "$td" != "$pd" ]; then SPOOF="YES"; fi
    if [ -n "$tv" ] && [ -n "$pv" ] && [ "$tv" != "$pv" ]; then SPOOF="YES"; fi
    if [ -n "$tl" ] && [ -n "$pl" ] && [ "$tl" != "$pl" ]; then SPOOF="YES"; fi

    # ---------- [6] 最终裁决（bltruth 规则） ----------
    VERDICT="UNKNOWN"
    if [ "$td" = "unlocked" ]; then
        # 真相源=unlocked：无论属性如何伪装
        VERDICT="UNLOCKED"
    elif [ "$td" = "locked" ]; then
        if [ "$SPOOF" = "YES" ]; then
            # 内核与属性矛盾 -> 检出属性伪造
            VERDICT="UNLOCKED"
        elif [ "$R" = "1" ] && [ -n "$LAST_FLAGS" ]; then
            case "$LAST_FLAGS" in
                00)
                    # flags 全零 + 属性侧一致 -> 原厂校验完整
                    if [ "$pv" = "green" ] || [ "$pd" = "locked" ]; then
                        VERDICT="LOCKED"
                    fi
                    ;;
                *)
                    # 非零关闭位 = 曾 fastboot 刷写关闭 AVB，仅解锁后可行
                    VERDICT="UNLOCKED"
                    ;;
            esac
        elif [ "$R" != "1" ]; then
            # 非 Root：全部可见证据一致指向锁定（中置信）
            if [ "$pv" = "green" ] || [ "$pd" = "locked" ]; then
                VERDICT="LOCKED"
            fi
        fi
    elif [ "$SPOOF" = "YES" ]; then
        # 真相源缺失但属性矛盾：伪造成 locked/green 的目标必是掩盖解锁
        if [ "$pd" = "locked" ] || [ "$pv" = "green" ]; then
            VERDICT="UNLOCKED"
        fi
    fi

    case "$VERDICT" in
        UNLOCKED) echo "BL=unlocked" ;;
        LOCKED)   echo "BL=locked" ;;
        *)        echo "BL=unknown" ;;
    esac
    exit 0
}

# =====================================================
# 主入口 - 命令分发
# =====================================================
COMMAND="$1"
shift 2>/dev/null || true

case "$COMMAND" in
    keybox)
        cmd_keybox "$@"
        ;;
    status)
        cmd_status "$@"
        ;;
    soft-reboot|softreboot)
        cmd_soft_reboot "$@"
        ;;
    deep-reboot|deepreboot)
        cmd_deep_reboot "$@"
        ;;
    clean-usb|usbclean)
        cmd_clean_usb "$@"
        ;;
    ts-pkg|tspkg)
        cmd_ts_pkg "$@"
        ;;
    hidden-apps|hidden)
        cmd_hidden_apps "$@"
        ;;
    hide-root|hideroot)
        cmd_hide_root "$@"
        ;;
    fix-network|fixnetwork)
        cmd_fix_network "$@"
        ;;
    jailbreak-hide|jailbreakhide)
        cmd_jailbreak_hide "$@"
        ;;
    hash|reset-hash)
        cmd_hash "$@"
        ;;
    fix-lsposed|lsposed)
        cmd_fix_lsposed "$@"
        ;;
    fix-recovery|twrp)
        cmd_fix_recovery "$@"
        ;;
    clean-all|cleanall)
        cmd_clean_all "$@"
        ;;
    clean-luna|luna|fix-niutou|niutou)
        cmd_clean_luna "$@"
        ;;
    fix-chunqiu|chunqiu)
        cmd_fix_chunqiu "$@"
        ;;
    fix-momo|momo)
        cmd_fix_momo "$@"
        ;;
    fix-hunter|hunter)
        cmd_fix_hunter "$@"
        ;;
    clean-traces|cleantraces)
        cmd_clean_traces "$@"
        ;;
    tee-burn|teeburn)
        cmd_tee_burn "$@"
        ;;
    usb-check|usbcheck)
        cmd_usb_check "$@"
        ;;
    usb-switch|usbswitch)
        cmd_usb_switch "$@"
        ;;
    *)
        echo "悲伤压缩包 - 合并工具脚本 v.01.90"
        echo "用法: sh tools.sh <command> [args...]"
        echo ""
        echo "可用命令:"
        echo "  keybox [渠道]   更新keybox文件 (github/local, 默认自动)"
        echo "  status          Root管理器与BL锁真实状态检测"
        echo "  soft-reboot     软重启(重启Zygote, 重载Zygisk/LSPosed)"
        echo "  deep-reboot     深度软重启(用户态重启, 属性存储重建)"
        echo "  clean-usb       清理USB调试痕迹"
        echo "  clean-traces    清理usb和玩机痕迹(合并版)"
        echo "  ts-pkg          更新TS包名列表"
        echo "  hidden-apps [1] 配置隐藏应用列表 (1=重启框架生效)"
        echo "  hide-root       一键配置隐藏Root"
        echo "  fix-network     修复越狱后无网络"
        echo "  jailbreak-hide  越狱隐藏环境(属性伪装+PID轮回+重启zygote)"
        echo "  hash <value>    重置哈希值"
        echo "  fix-lsposed     清理LSPosed Hook痕迹"
        echo "  fix-recovery    修复Twrp痕迹"
        echo "  clean-all       清理所有痕迹"
        echo "  clean-luna      清理Luna和牛头11异常"
        echo "  fix-chunqiu     修复春秋Found property"
        echo "  fix-momo        修复Momo SDK"
        echo "  fix-hunter      修复Hunter API"
        echo "  fix-niutou      修复牛头Hook/Root (同clean-luna)"
        echo "  tee-burn        TEE烧录密钥"
        echo "  usb-check       USB状态检测"
        echo "  usb-switch <target> <0|1>  USB开关 (adb/secure)"
        exit 1
        ;;
esac
