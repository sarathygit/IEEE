# Multi-stage build: the repo carries no Maven wrapper, so the build stage
# supplies Maven and the runtime stage carries only the JRE and the fat jar.
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build

# Dependencies first, so a source-only change reuses the cached layer.
COPY pom.xml .
RUN mvn -B -q dependency:go-offline

COPY src ./src
RUN mvn -B -q clean package -DskipTests

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=build /build/target/finguard-switch-1.0.0.jar app.jar

# The platform injects PORT; application.yml reads it (default 8081).
EXPOSE 8081

# Container-aware heap sizing: H2 is in-process, so the ledger lives in this
# heap alongside the application.
ENV JAVA_OPTS="-XX:MaxRAMPercentage=75"
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar app.jar"]
