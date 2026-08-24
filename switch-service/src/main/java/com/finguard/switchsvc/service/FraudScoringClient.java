package com.finguard.switchsvc.service;

import com.finguard.switchsvc.dto.ScoreRequest;
import com.finguard.switchsvc.dto.ScoreResponse;
import com.finguard.switchsvc.exception.PaymentException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

/**
 * The "microservice hop" (architecture step 3): synchronous call to the
 * FastAPI /score endpoint while the payment thread is suspended.
 */
@Service
public class FraudScoringClient {

    private static final Logger log = LoggerFactory.getLogger(FraudScoringClient.class);

    private final RestClient mlRestClient;

    public FraudScoringClient(RestClient mlRestClient) {
        this.mlRestClient = mlRestClient;
    }

    public ScoreResponse score(ScoreRequest request) {
        long t0 = System.nanoTime();
        try {
            ScoreResponse response = mlRestClient.post()
                    .uri("/score")
                    .body(request)
                    .retrieve()
                    .body(ScoreResponse.class);

            if (response == null) {
                throw PaymentException.scoringUnavailable(
                        new IllegalStateException("Empty body from /score"));
            }
            log.info("ML verdict: score={} is_fraud={} (hop {} ms, model inference {} ms)",
                    response.anomaly_score(), response.is_fraud(),
                    (System.nanoTime() - t0) / 1_000_000, response.processing_ms());
            return response;

        } catch (PaymentException e) {
            throw e;
        } catch (Exception e) {
            // Fail-closed: an unreachable or misbehaving scoring node means the
            // transaction is rejected, never silently waved through unscored.
            log.error("ML core unreachable after {} ms: {}",
                    (System.nanoTime() - t0) / 1_000_000, e.getMessage());
            throw PaymentException.scoringUnavailable(e);
        }
    }
}
