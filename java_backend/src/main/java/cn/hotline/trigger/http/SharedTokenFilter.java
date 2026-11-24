package cn.hotline.trigger.http;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Shared-secret check for every request entering the Java entry point.
 * An empty token disables the check, which keeps the current behaviour.
 */
public class SharedTokenFilter extends OncePerRequestFilter {

    public static final String TOKEN_HEADER = "X-Hotline-Token";
    private static final String UNAUTHORIZED_BODY =
            "{\"code\":\"UNAUTHORIZED\",\"message\":\"缺少或无效的访问令牌\"}";

    private final String expected;

    public SharedTokenFilter(String token) {
        this.expected = token == null ? "" : token.trim();
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        if (expected.isEmpty() || isPublic(request.getRequestURI())) {
            chain.doFilter(request, response);
            return;
        }
        String presented = request.getHeader(TOKEN_HEADER);
        if (!constantTimeEquals(presented, expected)) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json;charset=UTF-8");
            response.getOutputStream().write(UNAUTHORIZED_BODY.getBytes(StandardCharsets.UTF_8));
            return;
        }
        chain.doFilter(request, response);
    }

    private static boolean isPublic(String path) {
        return path.equals("/health/live") || path.equals("/health/ready")
                || path.startsWith("/health/live/") || path.startsWith("/health/ready/");
    }

    /** Constant-time comparison so the token cannot be guessed by timing. */
    private static boolean constantTimeEquals(String presented, String expected) {
        if (presented == null) {
            return false;
        }
        return MessageDigest.isEqual(presented.getBytes(StandardCharsets.UTF_8),
                expected.getBytes(StandardCharsets.UTF_8));
    }
}
