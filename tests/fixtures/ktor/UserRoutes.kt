package com.example.routes

import io.ktor.server.application.*
import io.ktor.server.routing.*
import io.ktor.server.response.*
import io.ktor.server.request.*
import io.ktor.http.*
import org.koin.ktor.ext.inject

data class User(val id: Int, val name: String)

class UserService {
    fun findAll(): List<User> = emptyList()
    fun findById(id: Int): User? = null
    fun create(user: User): User = user
}

fun Application.userRoutes() {
    val userService: UserService by inject()

    routing {
        route("/users") {
            get {
                call.respond(userService.findAll())
            }
            get("/{id}") {
                val id = call.parameters["id"]!!.toInt()
                call.respond(userService.findById(id) ?: HttpStatusCode.NotFound)
            }
            post {
                val user = call.receive<User>()
                call.respond(HttpStatusCode.Created, userService.create(user))
            }
        }
    }
}
