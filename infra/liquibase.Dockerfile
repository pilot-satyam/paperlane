FROM liquibase/liquibase:5.0.4-alpine
RUN lpm add postgresql --global
COPY db/changelog.sql /liquibase/paperlane/changelog.sql
