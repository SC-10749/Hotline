package cn.hotline;

import cn.hotline.trigger.http.SharedTokenFilter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.assertj.core.api.Assertions.assertThat;

class SharedTokenFilterTest {

    private static final String HEADER = "X-Hotline-Token";

    private boolean passes(String token, String path, String presented) throws Exception {
        var request = new MockHttpServletRequest("GET", path);
        if (presented != null) {
            request.addHeader(HEADER, presented);
        }
        var response = new MockHttpServletResponse();
        var chain = new FilterChain() {
            @Override
            public void doFilter(jakarta.servlet.ServletRequest req, jakarta.servlet.ServletResponse res)
                    throws IOException, ServletException {
                res.getWriter().write("passed");
            }
        };
        new SharedTokenFilter(token).doFilter(request, response, chain);
        return response.getStatus() == 200;
    }

    @Test void emptyTokenDisablesTheCheck() throws Exception {
        assertThat(passes("", "/harness/profile/credentials", null)).isTrue();
    }

    @Test void missingTokenIsRejected() throws Exception {
        assertThat(passes("secret", "/harness/profile/credentials", null)).isFalse();
    }

    @Test void wrongTokenIsRejected() throws Exception {
        assertThat(passes("secret", "/harness/profile/credentials", "nope")).isFalse();
    }

    @Test void correctTokenIsAccepted() throws Exception {
        assertThat(passes("secret", "/harness/profile/credentials", "secret")).isTrue();
    }

    @Test void healthEndpointsStayPublic() throws Exception {
        assertThat(passes("secret", "/health/live", null)).isTrue();
        assertThat(passes("secret", "/health/ready", null)).isTrue();
    }

    @Test void tokenComparisonIsCaseSensitive() throws Exception {
        assertThat(passes("secret", "/harness/profile/credentials", "SECRET")).isFalse();
    }
}
