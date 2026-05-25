package com.jarvisos.ghostmesh.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface ApiService {
    @GET("api/health")
    suspend fun health(): HealthResponse

    @POST("api/search")
    suspend fun search(@Body request: SearchRequest): SearchResponse

    @POST("api/people/search")
    suspend fun peopleSearch(@Body request: PeopleSearchRequest): PeopleResult
}
