import java.util.Properties
import groovy.json.JsonSlurper
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// The UI is the TV app's (tv/, built to tv/dist), bundled into the APK; so is its version (tv/package.json).
val tv: File = rootDir.resolve("../tv").canonicalFile
val tvVersion = (JsonSlurper().parse(tv.resolve("package.json")) as Map<*, *>)["version"] as String
val versionParts = tvVersion.split(".").map { part -> part.takeWhile(Char::isDigit).ifEmpty { "0" }.toInt() }

// Release signing (README "Release builds"): firetv/keystore.properties names the key; never committed.
val keystore = Properties().apply {
    val f = rootDir.resolve("keystore.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "media.bams.firetv"
    compileSdk = 35

    defaultConfig {
        applicationId = "media.bams.firetv"
        minSdk = 25        // Fire OS 6 (Android 7.1) and later; Fire OS 5 (2nd-gen stick and older) is too old for Media3
        targetSdk = 35
        versionCode = versionParts[0] * 10000 + versionParts[1] * 100 + versionParts[2]
        versionName = tvVersion
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

// tv/dist -> assets/www (the WebView loads file:///android_asset/www/index.html)
val copyWeb by tasks.registering(Copy::class) {
    val dist = tv.resolve("dist")
    doFirst {
        if (!dist.resolve("index.html").exists()) throw GradleException("tv/dist is missing: run `npm run build` in tv/ first.")
    }
    from(dist)
    into(layout.buildDirectory.dir("generated/web/www"))
}
tasks.named("preBuild") { dependsOn(copyWeb) }

dependencies {
    val media3 = "1.9.4"  // the last Media3 that builds against Android 15 (compileSdk 35); 1.10 needs 36
    implementation("androidx.media3:media3-exoplayer:$media3")
    implementation("androidx.media3:media3-exoplayer-hls:$media3")
    implementation("androidx.media3:media3-ui:$media3")
}
