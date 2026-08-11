/*
 * Copyright 2026 Google LLC.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package anthos.samples.bankofanthos.balancereader;

import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Loads PostgreSQL datasource properties from Google Cloud Secret Manager.
 */
public final class SecretManagerDataSourceLoader {

    private static final Logger LOGGER =
        LogManager.getLogger(SecretManagerDataSourceLoader.class);

    private SecretManagerDataSourceLoader() {
    }

    /**
     * Injects SPRING_DATASOURCE_* system properties from Secret Manager when configured.
     */
    public static void loadIfConfigured() {
        String secretId = System.getenv("LEDGER_DB_SECRET_ID");
        if (secretId == null || secretId.isBlank()) {
            LOGGER.info("LEDGER_DB_SECRET_ID not set; using SPRING_DATASOURCE_* env vars.");
            return;
        }

        String projectId = System.getenv("GCP_PROJECT");
        if (projectId == null || projectId.isBlank()) {
            projectId = System.getenv("GOOGLE_CLOUD_PROJECT");
        }
        if (projectId == null || projectId.isBlank()) {
            throw new IllegalStateException(
                "GCP_PROJECT or GOOGLE_CLOUD_PROJECT must be set when using Secret Manager");
        }

        LOGGER.info("Loading ledger database credentials from Secret Manager.");
        String payload = accessSecret(projectId, secretId);
        JsonObject credentials = JsonParser.parseString(payload).getAsJsonObject();

        setIfPresent("spring.datasource.url", credentials, "url");
        setIfPresent("spring.datasource.username", credentials, "username");
        setIfPresent("spring.datasource.password", credentials, "password");
    }

    private static String accessSecret(String projectId, String secretId) {
        try (SecretManagerServiceClient client = SecretManagerServiceClient.create()) {
            SecretVersionName versionName =
                SecretVersionName.of(projectId, secretId, "latest");
            return client.accessSecretVersion(versionName).getPayload()
                .getData().toStringUtf8();
        } catch (IOException ex) {
            throw new IllegalStateException("Failed to read ledger DB secret", ex);
        }
    }

    private static void setIfPresent(
            String propertyName, JsonObject credentials, String jsonKey) {
        if (!credentials.has(jsonKey)) {
            throw new IllegalStateException(
                String.format("Secret payload missing required field '%s'", jsonKey));
        }
        System.setProperty(propertyName, credentials.get(jsonKey).getAsString());
    }
}
