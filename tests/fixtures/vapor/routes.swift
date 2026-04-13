import Vapor

struct User: Content {
    var id: Int?
    var name: String
    var email: String
}

func routes(_ app: Application) throws {
    app.get("users") { req async throws -> [User] in
        return []
    }

    app.get("users", ":id") { req async throws -> User in
        let id = try req.parameters.require("id", as: Int.self)
        return User(id: id, name: "Test", email: "test@example.com")
    }

    app.post("users") { req async throws -> User in
        let user = try req.content.decode(User.self)
        return user
    }

    app.put("users", ":id") { req async throws -> User in
        let user = try req.content.decode(User.self)
        return user
    }

    app.delete("users", ":id") { req async throws -> HTTPStatus in
        return .noContent
    }
}
