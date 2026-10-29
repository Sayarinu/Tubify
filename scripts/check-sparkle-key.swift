// Validate the release trust anchor without printing private key material.
import Foundation
import CryptoKit

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

let encoded = (ProcessInfo.processInfo.environment["TUBIFY_SPARKLE_PRIVATE_KEY"] ?? "")
    .trimmingCharacters(in: .whitespacesAndNewlines)
guard let data = Data(base64Encoded: encoded), data.count == 64 else {
    fail("The Sparkle signing secret must contain a base64-encoded 64-byte seed/public-key pair.")
}
let key = try Curve25519.Signing.PrivateKey(rawRepresentation: data.prefix(32))
let expected = try String(contentsOfFile: CommandLine.arguments.last!, encoding: .utf8)
    .trimmingCharacters(in: .whitespacesAndNewlines)
guard key.publicKey.rawRepresentation.base64EncodedString() == expected else {
    fail("The Sparkle signing secret does not match the committed public key.")
}
