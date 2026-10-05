package com.stockmonitor.monitor;

import java.io.IOException;

public class HttpStatusException extends IOException {
    private final int code;

    public HttpStatusException(int code, String url) {
        super("HTTP " + code + " " + describe(code) + " - " + url);
        this.code = code;
    }

    public int code() {
        return code;
    }

    /** 403/429/541（Apple 风控）与 5xx 可重试；404 等客户端错误不重试。 */
    public boolean retryable() {
        return code == 403 || code == 429 || code == 541 || code >= 500;
    }

    public boolean throttled() {
        return code == 403 || code == 429 || code == 541;
    }

    private static String describe(int code) {
        return switch (code) {
            case 403, 541 -> "(部件号无效，或被 Apple 风控拦截)";
            case 429 -> "(请求过于频繁)";
            case 404 -> "(路径或部件号不存在)";
            default -> "";
        };
    }
}
