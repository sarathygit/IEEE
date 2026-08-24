package com.finguard.switchsvc.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.time.Duration;

/**
 * HTTP client wiring for the Python Predictive Intelligence Core.
 *
 * Timeouts are deliberately tight: the scoring hop happens while the payer's
 * ledger row is held under a pessimistic lock, so every millisecond spent
 * waiting here extends the account freeze. If the ML node cannot answer
 * within the read timeout the switch fails closed (rejects the payment)
 * rather than holding locks indefinitely.
 */
@Configuration
public class MlClientConfig {

    @Bean
    public RestClient mlRestClient(
            @Value("${finguard.ml.base-url}") String baseUrl,
            @Value("${finguard.ml.connect-timeout-ms:300}") long connectTimeoutMs,
            @Value("${finguard.ml.read-timeout-ms:1500}") long readTimeoutMs) {

        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(connectTimeoutMs));
        factory.setReadTimeout(Duration.ofMillis(readTimeoutMs));

        return RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}
