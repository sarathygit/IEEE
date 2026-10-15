package com.finguard.switchsvc.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * CORS policy for the switch's REST surface.
 *
 * Origins are configuration, not code, so the same artifact serves the local
 * React dev server and a deployed front-end. The default value reproduces the
 * previous hard-coded allow-list ({@code localhost:5173}, {@code localhost:3000}),
 * so local development is unaffected when no override is supplied.
 *
 * Patterns are matched with {@code allowedOriginPatterns}, which permits a
 * single wildcard label (e.g. {@code https://*.vercel.app} to cover preview
 * deployments). Credentials are not enabled: the switch authenticates each
 * payment with an MPIN in the request body, not with cookies.
 */
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    private final String[] allowedOrigins;

    public CorsConfig(
            @Value("${finguard.cors.allowed-origins:http://localhost:5173,http://localhost:3000}")
            String[] allowedOrigins) {
        this.allowedOrigins = allowedOrigins;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/v1/**")
                .allowedOriginPatterns(allowedOrigins)
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type")
                .allowCredentials(false)
                .maxAge(3600);
    }
}
