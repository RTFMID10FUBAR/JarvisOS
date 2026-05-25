package com.jarvisos.ghostmesh.data

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    private var _baseUrl = "http://10.0.2.2:8080/"
    private var _service: ApiService? = null

    fun getService(baseUrl: String = _baseUrl): ApiService {
        val normalized = baseUrl.trimEnd('/') + "/"
        if (_service == null || normalized != _baseUrl) {
            _baseUrl = normalized
            _service = buildService(normalized)
        }
        return _service!!
    }

    fun invalidate() {
        _service = null
    }

    private fun buildService(baseUrl: String): ApiService {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }
}
