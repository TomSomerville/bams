import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// The app's own pages (Downloads, Servers, offline): built from web/ (`npm run build:app` -> web/dist-app).
// Online the app shows each server's own web UI, so those pages aren't bundled.
val web: File = rootDir.resolve("../web").canonicalFile
val appVersion = providers.gradleProperty("bamsVersion").get()
val versionParts = appVersion.split(".").map { part -> part.takeWhile(Char::isDigit).ifEmpty { "0" }.toInt() }

// Release signing (README "Release builds"): android/keystore.properties names the key; never committed.
val keystore = Properties().apply {
    val f = rootDir.resolve("keystore.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "media.bams.phone"
    compileSdk = 35

    defaultConfig {
        applicationId = "media.bams.phone"
        minSdk = 26        // Android 8
        targetSdk = 35
        versionCode = versionParts[0] * 10000 + versionParts[1] * 100 + versionParts[2]
        versionName = appVersion
        resourceConfigurations += "en"  // the UI is English; drops the libraries' translations
    }

    signingConfigs {
        if (keystore.containsKey("storeFile")) {
            create("release") {
                storeFile = file(keystore.getProperty("storeFile"))
                storePassword = keystore.getProperty("storePassword")
                keyAlias = keystore.getProperty("keyAlias")
                keyPassword = keystore.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets["main"].assets.srcDir(layout.buildDirectory.dir("generated/web"))
}

kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

// web/dist-app -> assets/app (served as https://appassets.androidplatform.net/app/)
val copyWeb by tasks.registering(Copy::class) {
    val dist = web.resolve("dist-app")
    doFirst {
        if (!dist.resolve("index.html").exists()) throw GradleException("web/dist-app is missing: run `npm run build:app` in web/ first.")
    }
    from(dist)
    into(layout.buildDirectory.dir("generated/web/app"))
}
tasks.named("preBuild") { dependsOn(copyWeb) }

dependencies {
    val media3 = "1.9.4"  // the last Media3 that builds against Android 15 (compileSdk 35); 1.10 needs 36
    implementation("androidx.media3:media3-exoplayer:$media3")
    implementation("androidx.media3:media3-ui:$media3")
    implementation("androidx.media3:media3-session:$media3")
    implementation("androidx.webkit:webkit:1.12.1")
}
