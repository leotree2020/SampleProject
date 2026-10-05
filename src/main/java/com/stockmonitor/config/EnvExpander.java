package com.stockmonitor.config;

import java.util.Map;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 将配置文本中的 ${ENV} / ${ENV:默认值} 替换为环境变量。 */
public final class EnvExpander {
    private static final Pattern VAR = Pattern.compile("\\$\\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?}");

    private EnvExpander() {
    }

    public static String expand(String text) {
        return expand(text, System.getenv()::get);
    }

    static String expand(String text, Function<String, String> lookup) {
        Matcher m = VAR.matcher(text);
        StringBuilder sb = new StringBuilder();
        while (m.find()) {
            String value = lookup.apply(m.group(1));
            if (value == null) {
                value = m.group(2) != null ? m.group(2) : "";
            }
            m.appendReplacement(sb, Matcher.quoteReplacement(value));
        }
        m.appendTail(sb);
        return sb.toString();
    }

    public static String expand(String text, Map<String, String> env) {
        return expand(text, env::get);
    }
}
